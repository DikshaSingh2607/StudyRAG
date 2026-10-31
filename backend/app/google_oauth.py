from __future__ import annotations

import asyncio
import hmac
import logging
import os
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token as google_id_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import browser_origin, cookie_options, set_session_cookie
from .config import rate_limit_limit
from .db import get_db
from .models import AuthSession, GoogleOAuthState, User
from .rate_limit import enforce_rate_limit
from .security import new_id, new_secret, session_expiry, token_digest, utcnow

logger = logging.getLogger("studyrag.auth.google")
router = APIRouter(prefix="/api/auth", tags=["authentication"])

_STATE_COOKIE = "studyrag_google_state"
_NONCE_COOKIE = "studyrag_google_nonce"
_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def credentials() -> tuple[str, str] | None:
    client_id = os.getenv("STUDYRAG_GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("STUDYRAG_GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id and not client_secret:
        return None
    if not client_id or not client_secret:
        return None
    return client_id, client_secret


def _verify_id_token(raw_token: str, client_id: str) -> dict[str, object]:
    claims = google_id_token.verify_oauth2_token(raw_token, GoogleRequest(timeout=10), client_id)
    return claims


def _clear_flow_cookies(response: Response) -> None:
    for name in (_STATE_COOKIE, _NONCE_COOKIE):
        response.delete_cookie(name, httponly=True, **cookie_options())


def _oauth_failure(origin: str, detail: str = "") -> RedirectResponse:
    suffix = "#oauth=error"
    if detail == "cancelled":
        suffix = "#oauth=cancelled"
    response = RedirectResponse(f"{origin}/{suffix}", status_code=303)
    response.headers["Cache-Control"] = "no-store"
    _clear_flow_cookies(response)
    return response


@router.get("/providers")
async def providers() -> dict[str, bool]:
    return {"google": credentials() is not None}


@router.post("/google/start")
async def start_google(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    configured = credentials()
    if configured is None:
        raise HTTPException(status_code=404, detail="Google sign-in is not configured")
    await enforce_rate_limit(
        db, request, scope="google_start", subject="browser",
        account_limit=rate_limit_limit("GOOGLE", 10),
        ip_limit=rate_limit_limit("GOOGLE_IP", 100), ip_scope="google",
    )
    client_id, _ = configured
    origin = browser_origin(request)
    state = new_secret()
    nonce = new_secret()
    db.add(
        GoogleOAuthState(
            id=new_id(),
            state_hash=token_digest(state),
            nonce_hash=token_digest(nonce),
            origin=origin,
            expires_at=utcnow() + timedelta(minutes=10),
        )
    )
    await db.commit()
    options = cookie_options()
    response.set_cookie(_STATE_COOKIE, state, max_age=600, httponly=True, **options)
    response.set_cookie(_NONCE_COOKIE, nonce, max_age=600, httponly=True, **options)
    response.headers["Cache-Control"] = "no-store"
    callback_uri = f"{origin}/api/auth/google/callback"
    authorization_url = f"{_AUTH_ENDPOINT}?{urlencode({
        'client_id': client_id,
        'redirect_uri': callback_uri,
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'nonce': nonce,
        'prompt': 'select_account',
    })}"
    return {"authorization_url": authorization_url}


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Response:
    configured = credentials()
    if configured is None:
        raise HTTPException(status_code=404, detail="Google sign-in is not configured")
    await enforce_rate_limit(
        db, request, scope="google_callback", subject=token_digest(state or ""),
        account_limit=rate_limit_limit("GOOGLE_CALLBACK", 10),
        ip_limit=rate_limit_limit("GOOGLE_IP", 100), ip_scope="google",
    )
    client_id, client_secret = configured
    state_cookie = request.cookies.get(_STATE_COOKIE, "")
    nonce_cookie = request.cookies.get(_NONCE_COOKIE, "")
    if not state or not state_cookie or not nonce_cookie or not hmac.compare_digest(state, state_cookie):
        raise HTTPException(status_code=400, detail="Google sign-in could not be verified")

    flow = await db.scalar(select(GoogleOAuthState).where(GoogleOAuthState.state_hash == token_digest(state)))
    if flow is None or flow.used_at is not None or flow.expires_at <= utcnow():
        raise HTTPException(status_code=400, detail="Google sign-in has expired; try again")
    if not hmac.compare_digest(flow.nonce_hash, token_digest(nonce_cookie)):
        raise HTTPException(status_code=400, detail="Google sign-in could not be verified")

    flow.used_at = utcnow()
    await db.commit()
    origin = flow.origin
    if error:
        return _oauth_failure(origin, "cancelled" if error == "access_denied" else "")
    if not code:
        return _oauth_failure(origin)

    try:
        callback_uri = f"{origin}/api/auth/google/callback"
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=False) as client:
            token_response = await client.post(
                _TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": callback_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            token_response.raise_for_status()
            token_data = token_response.json()
        raw_id_token = token_data.get("id_token")
        if not isinstance(raw_id_token, str) or len(raw_id_token) > 20000:
            raise ValueError("Missing ID token")
        claims = await asyncio.to_thread(_verify_id_token, raw_id_token, client_id)
        issuer = claims.get("iss")
        subject = claims.get("sub")
        email = claims.get("email")
        if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
            raise ValueError("Unexpected issuer")
        if not isinstance(subject, str) or not subject or len(subject) > 255:
            raise ValueError("Invalid subject")
        if not isinstance(email, str) or len(email) > 320 or claims.get("email_verified") is not True:
            raise ValueError("Unverified account email")
        claim_nonce = claims.get("nonce")
        if not isinstance(claim_nonce, str) or not hmac.compare_digest(flow.nonce_hash, token_digest(claim_nonce)):
            raise ValueError("Invalid OIDC nonce")

        normalized_email = email.strip().lower()
        user = await db.scalar(select(User).where(User.google_subject == subject))
        if user is None:
            user = await db.scalar(select(User).where(User.email == normalized_email))
        if user is not None and user.is_disabled:
            raise PermissionError("Account is disabled")
        if user is not None and user.google_subject not in {None, subject}:
            raise PermissionError("Google identity is already linked")
        if user is None:
            full_name = claims.get("name")
            display_name = full_name.strip() if isinstance(full_name, str) and full_name.strip() else normalized_email.split("@", 1)[0]
            user = User(
                id=new_id(),
                email=normalized_email,
                display_name=display_name[:100],
                password_hash=None,
                google_subject=subject,
                role="student",
                is_verified=True,
                is_disabled=False,
            )
            db.add(user)
        else:
            user.google_subject = subject
            user.is_verified = True

        session_token = new_secret()
        db.add(AuthSession(id=new_id(), user_id=user.id, token_hash=token_digest(session_token), expires_at=session_expiry()))
        await db.commit()
        response = RedirectResponse(f"{origin}/#oauth=success", status_code=303)
        set_session_cookie(response, session_token)
        response.headers["Cache-Control"] = "no-store"
        _clear_flow_cookies(response)
        return response
    except Exception as exc:
        await db.rollback()
        logger.warning("Google sign-in failed (%s)", type(exc).__name__)
        return _oauth_failure(origin)
