"""Anonymous rate limiting.

V1 has no accounts, so limits are keyed to a salted hash of the client's
address. We never store a raw IP in PostgreSQL, and the Redis keys expire.

Different operations get different budgets: a video upload costs far more than
a status poll, so they cannot share a limit.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from enum import StrEnum

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.errors import RateLimitError
from app.core.logging import get_logger

logger = get_logger(__name__)


class RateLimitOperation(StrEnum):
    TEXT_SUBMISSION = "text_submission"
    URL_SUBMISSION = "url_submission"
    IMAGE_SUBMISSION = "image_submission"
    VIDEO_SUBMISSION = "video_submission"
    STATUS_POLL = "status_poll"
    SEARCH = "search"


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: int


def fingerprint_client(client_ip: str | None) -> str:
    """Hash a client address into a stable, non-reversible identifier.

    Salted so the hashes cannot be reversed with a rainbow table of the IPv4
    space -- an unsalted SHA-256 of an IP address is trivially invertible.
    """
    settings = get_settings()
    raw = f"{settings.client_fingerprint_salt}:{client_ip or 'unknown'}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class RateLimiter:
    """Fixed-window limiter backed by Redis.

    Fixed windows allow a burst at a boundary, which is acceptable here: this
    exists to stop resource exhaustion, not to shape traffic precisely. The
    tradeoff is one round trip instead of the several a sliding window needs.
    """

    def __init__(self, redis_client: aioredis.Redis | None = None) -> None:
        self._redis = redis_client

    async def _client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                get_settings().redis_url, encoding="utf-8", decode_responses=True
            )
        return self._redis

    def _limit_for(self, operation: RateLimitOperation) -> int:
        settings = get_settings()
        return {
            RateLimitOperation.TEXT_SUBMISSION: settings.rate_limit_text_submissions,
            RateLimitOperation.URL_SUBMISSION: settings.rate_limit_url_submissions,
            RateLimitOperation.IMAGE_SUBMISSION: settings.rate_limit_image_submissions,
            RateLimitOperation.VIDEO_SUBMISSION: settings.rate_limit_video_submissions,
            RateLimitOperation.STATUS_POLL: settings.rate_limit_status_polls,
            RateLimitOperation.SEARCH: settings.rate_limit_search,
        }[operation]

    async def check(self, operation: RateLimitOperation, client_ip: str | None) -> RateLimitResult:
        """Consume one unit of budget. Never raises on Redis failure."""
        settings = get_settings()
        limit = self._limit_for(operation)
        window = settings.rate_limit_window_seconds

        if not settings.rate_limit_enabled:
            return RateLimitResult(True, limit, limit, 0)

        fingerprint = fingerprint_client(client_ip)
        window_start = int(time.time()) // window
        key = f"ratelimit:{operation}:{fingerprint}:{window_start}"

        try:
            client = await self._client()
            pipe = client.pipeline()
            pipe.incr(key)
            # TTL set every time is harmless and means a key can never outlive
            # its window if the initial expire were ever lost.
            pipe.expire(key, window)
            count, _ = await pipe.execute()
        except Exception as exc:
            # Fail open. Redis being down should degrade abuse protection, not
            # take the whole service offline -- availability matters more here,
            # and the upload size caps still bound the damage.
            logger.warning("ratelimit.unavailable", error_type=type(exc).__name__)
            return RateLimitResult(True, limit, limit, 0)

        remaining = max(0, limit - int(count))
        reset_after = window - (int(time.time()) % window)
        return RateLimitResult(int(count) <= limit, limit, remaining, reset_after)

    async def enforce(self, operation: RateLimitOperation, client_ip: str | None) -> None:
        """Check and raise if over budget."""
        result = await self.check(operation, client_ip)
        if not result.allowed:
            raise RateLimitError(
                "Too many requests. Please wait before trying again.",
                retry_after_seconds=result.reset_after_seconds,
                details={"limit": result.limit, "operation": operation.value},
            )

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter
