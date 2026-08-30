"""Shared route dependencies."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.ids import VERIFICATION_PREFIX, is_valid_public_id
from app.db.session import get_db
from app.services.rate_limit import RateLimitOperation, get_rate_limiter


async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session


def client_ip(request: Request) -> str | None:
    """Best-effort client address for rate limiting.

    Never stored raw -- it is immediately salted and hashed. Proxy headers are
    honored only for the first hop; a client can forge X-Forwarded-For, so this
    is abuse mitigation, not an identity claim.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else None


def validate_verification_id(public_id: str) -> str:
    """Validate id shape before it reaches a query.

    Rejects malformed ids early with a clean 400 rather than letting them
    produce a confusing database error.
    """
    if not is_valid_public_id(public_id, VERIFICATION_PREFIX):
        raise ValidationError("That verification id is not valid.", {"public_id": public_id[:64]})
    return public_id


def rate_limit(operation: RateLimitOperation):  # type: ignore[no-untyped-def]
    """Build a dependency enforcing one operation's budget."""

    async def _dependency(request: Request) -> None:
        await get_rate_limiter().enforce(operation, client_ip(request))

    return _dependency


__all__ = [
    "Depends",
    "NotFoundError",
    "client_ip",
    "db_session",
    "rate_limit",
    "validate_verification_id",
]
