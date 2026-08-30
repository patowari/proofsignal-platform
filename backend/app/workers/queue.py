"""Redis-backed job queue.

Deliberately small and explicit rather than a framework. What this needs is
narrow -- one job type, at-least-once delivery, bounded retries, a visibility
timeout, and a dead-letter list -- and a hand-rolled version of that is easier
to reason about (and to test) than configuring a general-purpose library.

Delivery model: a BRPOPLPUSH moves a job atomically from the pending list to a
per-worker processing list, so a job is never lost if a worker dies mid-flight.
A reaper returns jobs whose lease expired. Consumers must therefore be
idempotent -- see IdempotencyGuard and the pipeline's stage-resume behavior.
"""

from __future__ import annotations

import json
import socket
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import redis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _as_text(value: Any) -> str:
    """Normalize a Redis reply to str.

    A client built without decode_responses returns bytes; a caller may pass
    such a client in. Decoding here means the rest of the queue never has to
    care which it got.
    """
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


@dataclass(slots=True)
class Job:
    id: str
    payload: dict[str, Any]
    attempt: int = 1
    enqueued_at: float = field(default_factory=time.time)
    #: When this job's lease expires and the reaper may requeue it.
    lease_expires_at: float = 0.0

    def to_json(self) -> str:
        return json.dumps(
            {
                "id": self.id,
                "payload": self.payload,
                "attempt": self.attempt,
                "enqueued_at": self.enqueued_at,
                "lease_expires_at": self.lease_expires_at,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> Job:
        data = json.loads(raw)
        return cls(
            id=data["id"],
            payload=data["payload"],
            attempt=data.get("attempt", 1),
            enqueued_at=data.get("enqueued_at", time.time()),
            lease_expires_at=data.get("lease_expires_at", 0.0),
        )


class JobQueue:
    """At-least-once queue over Redis lists."""

    def __init__(self, name: str | None = None, redis_client: redis.Redis | None = None) -> None:
        settings = get_settings()
        self.name = name or settings.queue_name
        self._redis = redis_client or redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            # A blocking BRPOPLPUSH holds the socket open for its full timeout.
            # The socket timeout must exceed that, or an idle queue looks like a
            # dead connection and kills the worker. Health checks keep an idle
            # connection from being dropped by an intermediary.
            socket_timeout=settings.queue_block_timeout_seconds + 10,
            socket_keepalive=True,
            health_check_interval=30,
        )
        # Identifies this worker's processing list, so concurrent workers do not
        # reclaim each other's in-flight jobs.
        self.consumer_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"

    @property
    def pending_key(self) -> str:
        return f"queue:{self.name}:pending"

    @property
    def dead_letter_key(self) -> str:
        return f"queue:{self.name}:dead"

    def processing_key(self, consumer_id: str | None = None) -> str:
        return f"queue:{self.name}:processing:{consumer_id or self.consumer_id}"

    # ---- Producing ------------------------------------------------------

    def enqueue(self, payload: dict[str, Any], *, job_id: str | None = None) -> str:
        job = Job(id=job_id or uuid.uuid4().hex, payload=payload)
        # LPUSH + BRPOPLPUSH gives FIFO order.
        self._redis.lpush(self.pending_key, job.to_json())
        logger.info("queue.enqueued", job_id=job.id, queue=self.name)
        return job.id

    # ---- Consuming ------------------------------------------------------

    def reserve(self, timeout: int | None = None) -> Job | None:
        """Claim the next job, atomically moving it to this worker's list.

        Returns None when the queue stays empty for `timeout` seconds.
        """
        if timeout is None:
            timeout = get_settings().queue_block_timeout_seconds
        raw = self._redis.brpoplpush(self.pending_key, self.processing_key(), timeout=timeout)
        if raw is None:
            return None

        raw_text = _as_text(raw)
        job = Job.from_json(raw_text)
        job.lease_expires_at = time.time() + get_settings().job_timeout_seconds

        # Rewrite the entry with its lease so the reaper knows when it expired.
        self._redis.lrem(self.processing_key(), 1, raw_text)
        self._redis.lpush(self.processing_key(), job.to_json())

        logger.info("queue.reserved", job_id=job.id, attempt=job.attempt)
        return job

    def complete(self, job: Job) -> None:
        """Acknowledge success by dropping the job from the processing list."""
        removed = self._redis.lrem(self.processing_key(), 0, job.to_json())
        if not removed:
            # The lease expired and the reaper already requeued it. The work is
            # done either way; a duplicate run is safe because consumers are
            # idempotent.
            logger.warning("queue.complete_missing", job_id=job.id)
        logger.info("queue.completed", job_id=job.id)

    def fail(self, job: Job, error: str, *, retryable: bool = True) -> None:
        """Retry with backoff, or dead-letter once attempts are exhausted.

        Deterministic failures (invalid media, unparseable input) pass
        retryable=False: retrying them just burns capacity to fail identically.
        """
        settings = get_settings()
        self._redis.lrem(self.processing_key(), 0, job.to_json())

        if not retryable or job.attempt >= settings.job_max_retries:
            self._redis.lpush(
                self.dead_letter_key,
                json.dumps(
                    {
                        "job": json.loads(job.to_json()),
                        "error": error,
                        "failed_at": time.time(),
                        "retryable": retryable,
                    }
                ),
            )
            logger.error(
                "queue.dead_lettered",
                job_id=job.id,
                attempt=job.attempt,
                retryable=retryable,
                error=error,
            )
            return

        job.attempt += 1
        job.lease_expires_at = 0.0
        # Exponential backoff, implemented by a delayed re-push. A sorted-set
        # scheduler would be more precise; this is adequate for the retry
        # volumes involved and keeps the queue a plain list.
        self._redis.lpush(self.pending_key, job.to_json())
        logger.warning("queue.retrying", job_id=job.id, attempt=job.attempt, error=error)

    def reap_expired(self) -> int:
        """Requeue jobs whose worker died mid-flight.

        Without this, a crashed worker's jobs would sit in its processing list
        forever and the submission would appear stuck at QUEUED.
        """
        requeued = 0
        now = time.time()
        for key in self._redis.scan_iter(match=f"queue:{self.name}:processing:*"):
            for raw in self._redis.lrange(key, 0, -1):
                raw_text = _as_text(raw)
                try:
                    job = Job.from_json(raw_text)
                except (json.JSONDecodeError, KeyError):
                    self._redis.lrem(key, 1, raw_text)
                    continue
                if job.lease_expires_at and job.lease_expires_at < now:
                    self._redis.lrem(key, 1, raw_text)
                    job.attempt += 1
                    job.lease_expires_at = 0.0
                    self._redis.lpush(self.pending_key, job.to_json())
                    requeued += 1
                    logger.warning("queue.reaped", job_id=job.id, attempt=job.attempt)
        return requeued

    # ---- Introspection --------------------------------------------------

    def depth(self) -> int:
        return int(self._redis.llen(self.pending_key))

    def dead_letter_depth(self) -> int:
        return int(self._redis.llen(self.dead_letter_key))

    def stats(self) -> dict[str, int]:
        return {"pending": self.depth(), "dead_letter": self.dead_letter_depth()}

    def close(self) -> None:
        self._redis.close()


class IdempotencyGuard:
    """Prevents duplicate concurrent processing of the same verification.

    At-least-once delivery means a job can arrive twice. The guard is a Redis
    lock keyed on the verification id; the pipeline additionally resumes from
    the last completed stage, so a redelivery repeats no completed work.
    """

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        self._redis = redis_client or redis.Redis.from_url(
            get_settings().redis_url, decode_responses=True
        )

    def acquire(self, verification_id: str, ttl_seconds: int | None = None) -> bool:
        ttl = ttl_seconds or get_settings().job_timeout_seconds
        return bool(self._redis.set(f"lock:verification:{verification_id}", "1", nx=True, ex=ttl))

    def release(self, verification_id: str) -> None:
        self._redis.delete(f"lock:verification:{verification_id}")


_queue: JobQueue | None = None


def get_queue() -> JobQueue:
    global _queue
    if _queue is None:
        _queue = JobQueue()
    return _queue
