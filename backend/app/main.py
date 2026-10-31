from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import router as auth_router
from .courses import router as courses_router
from .db import dispose_engine, session_factory
from .google_oauth import router as google_oauth_router
from .security import require_csrf

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("studyrag")


class SecurityHeadersAndCsrf(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            try:
                require_csrf(request)
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await dispose_engine()


app = FastAPI(title="StudyRAG", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(SecurityHeadersAndCsrf)
app.include_router(auth_router)
app.include_router(google_oauth_router)
app.include_router(courses_router)


@app.exception_handler(DBAPIError)
async def database_unavailable(_request: Request, exc: DBAPIError) -> JSONResponse:
    logger.warning("database request failed (%s)", type(exc).__name__)
    return JSONResponse(
        {"detail": "The course database is temporarily unreachable. Please try again shortly."},
        status_code=503,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health/ready")
async def ready() -> dict[str, str]:
    try:
        async with session_factory()() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        logger.warning("readiness check failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Required service unavailable") from exc


_STATIC = Path(__file__).resolve().parent / "static"


@app.get("/{path:path}")
async def frontend(path: str = ""):
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    if _STATIC.is_dir():
        candidate = (_STATIC / path).resolve()
        if candidate.is_relative_to(_STATIC.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        index = _STATIC / "index.html"
        if index.is_file():
            return FileResponse(index)
    raise HTTPException(status_code=404, detail="StudyRAG frontend is served by the Vite development server")
