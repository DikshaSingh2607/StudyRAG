from __future__ import annotations

from typing import Any
from datetime import timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .config import cookie_samesite, cookie_secure, frontend_url, rate_limit_limit
from .db import get_db
from .mailer import send_email
from .models import AuthSession, AuthToken, User
from .rate_limit import enforce_rate_limit
from .schemas import EmailIn, LoginIn, MessageOut, ResetPasswordIn, SignupIn, TokenIn
from .security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    current_user,
    hash_password,
    new_id,
    new_secret,
    session_expiry,
    token_digest,
    utcnow,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


def browser_origin(request: Request) -> str:
    raw = request.headers.get("origin", "")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="A valid browser origin is required")
    if parsed.path or parsed.query or parsed.fragment:
        raise HTTPException(status_code=400, detail="Invalid browser origin")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(status_code=400, detail="Secure origin required")
    return f"{parsed.scheme}://{parsed.netloc}"


def cookie_options() -> dict[str, Any]:
    return {"secure": cookie_secure(), "samesite": cookie_samesite(), "path": "/"}


def set_session_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        raw,
        max_age=14 * 24 * 60 * 60,
        httponly=True,
        **cookie_options(),
    )


def set_csrf_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        CSRF_COOKIE,
        raw,
        max_age=8 * 60 * 60,
        httponly=False,
        **cookie_options(),
    )


async def issue_auth_token(db: AsyncSession, user: User, purpose: str, lifetime: timedelta) -> str:
    await db.execute(
        update(AuthToken)
        .where(AuthToken.user_id == user.id, AuthToken.purpose == purpose, AuthToken.used_at.is_(None))
        .values(used_at=utcnow())
    )
    raw = new_secret()
    db.add(
        AuthToken(
            id=new_id(),
            user_id=user.id,
            purpose=purpose,
            token_hash=token_digest(raw),
            expires_at=utcnow() + lifetime,
        )
    )
    return raw


async def send_verification(db: AsyncSession, user: User, origin: str) -> None:
    token = await issue_auth_token(db, user, "verify_email", timedelta(hours=24))
    await db.commit()
    await send_email(
        user.email,
        "Verify your StudyRAG email",
        f"Hi {user.display_name},\n\nVerify your email using this one-time link (valid for 24 hours):\n{origin}/#verify={token}\n\nIf you did not create this account, you can ignore this message.\n",
    )


@router.get("/csrf")
async def csrf_bootstrap(request: Request, response: Response) -> dict[str, str]:
    token = request.cookies.get(CSRF_COOKIE)
    if not token or len(token) < 32:
        token = new_secret()
        set_csrf_cookie(response, token)
    response.headers["Cache-Control"] = "no-store"
    return {"csrf_token": token}


@router.post("/signup", status_code=202, response_model=MessageOut)
async def signup(payload: SignupIn, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    browser_origin(request)
    origin = frontend_url()
    email = str(payload.email).strip().lower()
    await enforce_rate_limit(
        db, request, scope="signup", subject=email,
        account_limit=rate_limit_limit("SIGNUP", 5),
        ip_limit=rate_limit_limit("SIGNUP_IP", 100), ip_scope="email",
    )
    exists = await db.scalar(select(User.id).where(User.email == email))
    if exists:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(
        id=new_id(),
        email=email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role="student",
        is_verified=False,
        is_disabled=False,
    )
    db.add(user)
    try:
        await db.flush()
        token = await issue_auth_token(db, user, "verify_email", timedelta(hours=24))
        await db.commit()
        await send_email(
            user.email,
            "Verify your StudyRAG email",
            f"Hi {user.display_name},\n\nVerify your email using this one-time link (valid for 24 hours):\n{origin}/#verify={token}\n\nIf you did not create this account, you can ignore this message.\n",
        )
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        # The user/token were committed before email delivery. Preserve the account and return an actionable error.
        raise HTTPException(
            status_code=503,
            detail="Account could not be created or its verification email could not be sent. Check the email service and try again.",
        ) from exc
    return {"message": "If this address can receive mail, a verification link has been sent."}


@router.post("/verify", response_model=MessageOut)
async def verify_email(payload: TokenIn, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await enforce_rate_limit(
        db, request, scope="verify", subject=token_digest(payload.token),
        account_limit=rate_limit_limit("VERIFY", 10),
        ip_limit=rate_limit_limit("VERIFY_IP", 100),
    )
    row = await db.scalar(
        select(AuthToken).where(
            AuthToken.token_hash == token_digest(payload.token),
            AuthToken.purpose == "verify_email",
            AuthToken.used_at.is_(None),
        )
    )
    if row is None or row.expires_at <= utcnow():
        raise HTTPException(status_code=400, detail="Verification link is invalid or expired")
    user = await db.get(User, row.user_id)
    if user is None or user.is_disabled:
        raise HTTPException(status_code=400, detail="Verification link is invalid or expired")
    user.is_verified = True
    row.used_at = utcnow()
    await db.commit()
    return {"message": "Email verified. You can now sign in."}


@router.post("/verification/resend", status_code=202, response_model=MessageOut)
async def resend_verification(payload: EmailIn, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    browser_origin(request)
    origin = frontend_url()
    email = str(payload.email).strip().lower()
    await enforce_rate_limit(
        db, request, scope="verification_resend", subject=email,
        account_limit=rate_limit_limit("EMAIL", 3),
        ip_limit=rate_limit_limit("EMAIL_IP", 100), ip_scope="email",
    )
    user = await db.scalar(select(User).where(User.email == email))
    if user is not None and not user.is_verified and not user.is_disabled:
        try:
            await send_verification(db, user, origin)
        except Exception:
            await db.rollback()
    return {"message": "If an unverified account exists for this address, a verification link has been sent."}


@router.post("/login", response_model=MessageOut)
async def login(payload: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    email = str(payload.email).strip().lower()
    await enforce_rate_limit(
        db, request, scope="login", subject=email,
        account_limit=rate_limit_limit("LOGIN", 10),
        ip_limit=rate_limit_limit("LOGIN_IP", 300),
    )
    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not user.password_hash or not verify_password(user.password_hash, payload.password):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    if user.is_disabled:
        raise HTTPException(status_code=403, detail="This account is disabled")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Verify your email before signing in")
    raw = new_secret()
    db.add(AuthSession(id=new_id(), user_id=user.id, token_hash=token_digest(raw), expires_at=session_expiry()))
    await db.commit()
    set_session_cookie(response, raw)
    response.headers["Cache-Control"] = "no-store"
    return {"message": "Signed in"}


@router.post("/logout", response_model=MessageOut)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        await db.execute(delete(AuthSession).where(AuthSession.token_hash == token_digest(raw)))
        await db.commit()
    response.delete_cookie(SESSION_COOKIE, **cookie_options(), httponly=True)
    response.headers["Cache-Control"] = "no-store"
    return {"message": "Signed out"}


@router.get("/me")
async def me(user: User = Depends(current_user)) -> dict[str, str]:
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role}


@router.post("/password/forgot", status_code=202, response_model=MessageOut)
async def forgot_password(payload: EmailIn, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    browser_origin(request)
    origin = frontend_url()
    email = str(payload.email).strip().lower()
    await enforce_rate_limit(
        db, request, scope="password_forgot", subject=email,
        account_limit=rate_limit_limit("EMAIL", 3),
        ip_limit=rate_limit_limit("EMAIL_IP", 100), ip_scope="email",
    )
    user = await db.scalar(select(User).where(User.email == email))
    if user is not None and user.is_verified and not user.is_disabled:
        try:
            token = await issue_auth_token(db, user, "reset_password", timedelta(minutes=30))
            await db.commit()
            await send_email(
                user.email,
                "Reset your StudyRAG password",
                f"A password reset was requested for your account. Use this one-time link within 30 minutes:\n{origin}/#reset={token}\n\nIf you did not request this, ignore this message.\n",
            )
        except Exception:
            await db.rollback()
    return {"message": "If a verified account exists for this address, password reset instructions have been sent."}


@router.post("/password/reset", response_model=MessageOut)
async def reset_password(payload: ResetPasswordIn, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await enforce_rate_limit(
        db, request, scope="password_reset", subject=token_digest(payload.token),
        account_limit=rate_limit_limit("RESET", 5),
        ip_limit=rate_limit_limit("RESET_IP", 100),
    )
    row = await db.scalar(
        select(AuthToken).where(
            AuthToken.token_hash == token_digest(payload.token),
            AuthToken.purpose == "reset_password",
            AuthToken.used_at.is_(None),
        )
    )
    if row is None or row.expires_at <= utcnow():
        raise HTTPException(status_code=400, detail="Reset link is invalid or expired")
    user = await db.get(User, row.user_id)
    if user is None or user.is_disabled:
        raise HTTPException(status_code=400, detail="Reset link is invalid or expired")
    user.password_hash = hash_password(payload.password)
    row.used_at = utcnow()
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    await db.commit()
    return {"message": "Password reset. You can now sign in."}
