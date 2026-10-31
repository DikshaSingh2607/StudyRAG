from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import AuthSession, User

_password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
SESSION_COOKIE = "studyrag_session"
CSRF_COOKIE = "studyrag_csrf"
SESSION_DAYS = 14


def new_id() -> str:
    return str(uuid.uuid4())


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise HTTPException(status_code=401, detail="Authentication required")
    session = await db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(raw)))
    if session is None or session.expires_at <= utcnow():
        raise HTTPException(status_code=401, detail="Session expired")
    user = await db.get(User, session.user_id)
    if user is None or user.is_disabled or not user.is_verified:
        raise HTTPException(status_code=401, detail="Account unavailable")
    return user


def require_csrf(request: Request) -> None:
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get("x-csrf-token", "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="Request token missing or invalid")
    fetch_site = request.headers.get("sec-fetch-site", "")
    if fetch_site == "cross-site":
        raise HTTPException(status_code=403, detail="Cross-site request blocked")


def session_expiry() -> datetime:
    return utcnow() + timedelta(days=SESSION_DAYS)
