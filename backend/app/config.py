from __future__ import annotations

import os
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url


def database_url() -> str:
    value = os.getenv("STUDYRAG_POSTGRES_URL", "").strip()
    if not value:
        raise RuntimeError("STUDYRAG_POSTGRES_URL is required")
    if value.startswith("postgres://"):
        value = "postgresql+asyncpg://" + value[len("postgres://"):]
    elif value.startswith("postgresql://"):
        value = "postgresql+asyncpg://" + value[len("postgresql://"):]
    parsed = make_url(value)
    if parsed.drivername not in {"postgresql+asyncpg", "postgresql"}:
        raise RuntimeError("STUDYRAG_POSTGRES_URL must point to PostgreSQL")
    if parsed.drivername == "postgresql":
        parsed = parsed.set(drivername="postgresql+asyncpg")
    query = dict(parsed.query)
    sslmode = query.pop("sslmode", None)
    if sslmode is not None and "ssl" not in query:
        query["ssl"] = sslmode
    return parsed.set(query=query).render_as_string(hide_password=False)


def cookie_secure() -> bool:
    return os.getenv("STUDYRAG_COOKIE_SECURE", "true").lower() == "true"


def cookie_samesite() -> str:
    value = os.getenv("STUDYRAG_COOKIE_SAMESITE", "none").lower()
    if value not in {"none", "lax", "strict"}:
        raise RuntimeError("STUDYRAG_COOKIE_SAMESITE must be none, lax, or strict")
    if value == "none" and not cookie_secure():
        raise RuntimeError("SameSite=None requires a Secure cookie")
    return value


def resend_settings() -> tuple[str, str]:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("STUDYRAG_EMAIL_FROM", "").strip()
    if not api_key or "\n" in api_key or "\r" in api_key:
        raise RuntimeError("RESEND_API_KEY is required for email delivery")
    if not sender:
        raise RuntimeError("STUDYRAG_EMAIL_FROM is required for email delivery")
    if "\n" in sender or "\r" in sender:
        raise RuntimeError("Invalid STUDYRAG_EMAIL_FROM")
    return api_key, sender


def frontend_url() -> str:
    default_url = "https://studyrag-frontendd.vercel.app"
    raw = (os.getenv("STUDYRAG_FRONTEND_URL", "").strip() or default_url).rstrip("/")
    if not raw or any(character.isspace() for character in raw):
        raise RuntimeError("Invalid STUDYRAG_FRONTEND_URL")
    try:
        parsed = urlsplit(raw)
        _ = parsed.port
    except ValueError as exc:
        raise RuntimeError("Invalid STUDYRAG_FRONTEND_URL") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("Invalid STUDYRAG_FRONTEND_URL")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("STUDYRAG_FRONTEND_URL must use HTTPS outside localhost")
    return raw


def rate_limit_window_seconds() -> int:
    raw = os.getenv("STUDYRAG_RATE_LIMIT_WINDOW_SECONDS", "900").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("STUDYRAG_RATE_LIMIT_WINDOW_SECONDS must be an integer") from exc
    if not 60 <= value <= 86400:
        raise RuntimeError("STUDYRAG_RATE_LIMIT_WINDOW_SECONDS must be between 60 and 86400")
    return value


def rate_limit_limit(name: str, default: int) -> int:
    if not name.replace("_", "").isalnum():
        raise RuntimeError("Invalid rate-limit name")
    raw = os.getenv(f"STUDYRAG_RATE_LIMIT_{name.upper()}", str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"STUDYRAG_RATE_LIMIT_{name.upper()} must be an integer") from exc
    if not 1 <= value <= 100000:
        raise RuntimeError(f"STUDYRAG_RATE_LIMIT_{name.upper()} must be between 1 and 100000")
    return value


def trusted_proxy_cidrs() -> tuple[str, ...]:
    raw = os.getenv("STUDYRAG_TRUSTED_PROXY_CIDRS", "").strip()
    if not raw:
        return ()
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    try:
        import ipaddress

        for value in values:
            ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise RuntimeError("STUDYRAG_TRUSTED_PROXY_CIDRS contains an invalid CIDR") from exc
    return values


def rate_limit_hash_key() -> bytes:
    # Prefer a dedicated key; the app-owned PostgreSQL DSN is the safe fallback.
    value = os.getenv("STUDYRAG_RATE_LIMIT_HMAC_KEY", "").strip()
    if not value:
        value = os.getenv("STUDYRAG_POSTGRES_URL", "").strip()
    if not value:
        raise RuntimeError("A PostgreSQL DSN or STUDYRAG_RATE_LIMIT_HMAC_KEY is required")
    return value.encode("utf-8")
