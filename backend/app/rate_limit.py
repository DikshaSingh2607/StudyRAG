from __future__ import annotations

import hashlib
import hmac
import ipaddress
from datetime import datetime, timedelta, timezone
from typing import Iterable

from fastapi import HTTPException, Request
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .config import rate_limit_hash_key, rate_limit_window_seconds, trusted_proxy_cidrs
from .models import RateLimitBucket
from .security import utcnow


def client_address(
    peer_address: str,
    forwarded_for: str | None,
    trusted_cidrs: Iterable[str] | None = None,
) -> str:
    try:
        peer = ipaddress.ip_address(peer_address)
    except ValueError:
        return "unknown"

    cidrs = tuple(trusted_cidrs) if trusted_cidrs is not None else trusted_proxy_cidrs()
    try:
        networks = tuple(ipaddress.ip_network(cidr.strip(), strict=False) for cidr in cidrs if cidr.strip())
    except ValueError:
        # A misconfigured trust list must not turn arbitrary forwarding headers into identity.
        networks = ()
    is_trusted = lambda address: any(address.version == network.version and address in network for network in networks)
    if not is_trusted(peer) or not forwarded_for or len(forwarded_for) > 2048:
        return peer.compressed

    forwarded: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    parts = forwarded_for.split(",")
    if len(parts) > 16:
        return peer.compressed
    try:
        forwarded = [ipaddress.ip_address(part.strip()) for part in parts]
    except ValueError:
        return peer.compressed

    # Walk from the app-facing proxy toward the client; only configured proxy hops are skipped.
    for address in reversed([*forwarded, peer]):
        if not is_trusted(address):
            return address.compressed
    return peer.compressed


def request_client_address(request: Request) -> str:
    peer = request.client.host if request.client is not None else "unknown"
    return client_address(peer, request.headers.get("x-forwarded-for"))


def bucket_digest(scope: str, subject: str, address: str, key: bytes) -> str:
    message = f"{scope}\0{subject.strip().casefold()}\0{address}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


async def _increment_bucket(db: AsyncSession, key_hash: str, window_start, now) -> int:
    same_window = RateLimitBucket.window_start == window_start
    statement = (
        insert(RateLimitBucket)
        .values(key_hash=key_hash, window_start=window_start, hit_count=1, updated_at=now)
        .on_conflict_do_update(
            index_elements=[RateLimitBucket.key_hash],
            set_={
                "window_start": case((same_window, RateLimitBucket.window_start), else_=window_start),
                "hit_count": case((same_window, RateLimitBucket.hit_count + 1), else_=1),
                "updated_at": now,
            },
        )
        .returning(RateLimitBucket.hit_count)
    )
    count = await db.scalar(statement)
    if count is None:
        raise RuntimeError("Rate-limit bucket update returned no count")
    return int(count)


async def enforce_rate_limit(
    db: AsyncSession,
    request: Request,
    *,
    scope: str,
    subject: str,
    account_limit: int,
    ip_limit: int,
    ip_scope: str | None = None,
) -> None:
    now = utcnow()
    window_seconds = rate_limit_window_seconds()
    window_epoch = int(now.timestamp()) // window_seconds * window_seconds
    window_start = datetime.fromtimestamp(window_epoch, tz=timezone.utc)
    address = request_client_address(request)
    key = rate_limit_hash_key()

    subject_count = await _increment_bucket(
        db,
        bucket_digest(scope, subject, address, key),
        window_start,
        now,
    )
    ip_count = await _increment_bucket(
        db,
        bucket_digest(ip_scope or f"{scope}:ip", "*", address, key),
        window_start,
        now,
    )
    # Keep only recently active pseudonymous buckets; this is a small indexed delete at the cohort scale.
    await db.execute(delete(RateLimitBucket).where(RateLimitBucket.updated_at < now - timedelta(days=1)))
    await db.commit()

    if subject_count > account_limit or ip_count > ip_limit:
        elapsed = int(now.timestamp()) % window_seconds
        retry_after = max(1, window_seconds - elapsed)
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )
