"""Job queue tests.

Runs against fakeredis, so the queue's delivery semantics are verified without
Docker. The behaviors that matter are the failure ones: a job must survive a
worker crash, and a poison job must not loop forever.
"""

from __future__ import annotations

import time

from app.workers.queue import IdempotencyGuard, Job, JobQueue


class TestEnqueueReserve:
    def test_enqueue_then_reserve(self, job_queue: JobQueue) -> None:
        job_queue.enqueue({"verification_public_id": "vfy_test1"})
        assert job_queue.depth() == 1

        job = job_queue.reserve(timeout=1)
        assert job is not None
        assert job.payload["verification_public_id"] == "vfy_test1"
        # Reserved jobs leave the pending list immediately.
        assert job_queue.depth() == 0

    def test_reserve_on_empty_queue_returns_none(self, job_queue: JobQueue) -> None:
        assert job_queue.reserve(timeout=1) is None

    def test_fifo_order(self, job_queue: JobQueue) -> None:
        for i in range(5):
            job_queue.enqueue({"verification_public_id": f"vfy_{i}"})
        seen = [job_queue.reserve(timeout=1).payload["verification_public_id"] for _ in range(5)]  # type: ignore[union-attr]
        assert seen == [f"vfy_{i}" for i in range(5)]

    def test_complete_removes_from_processing(self, job_queue: JobQueue) -> None:
        job_queue.enqueue({"verification_public_id": "vfy_x"})
        job = job_queue.reserve(timeout=1)
        assert job is not None
        job_queue.complete(job)
        assert job_queue.depth() == 0
        assert job_queue.dead_letter_depth() == 0


class TestRetries:
    def test_transient_failure_is_retried(self, job_queue: JobQueue) -> None:
        job_queue.enqueue({"verification_public_id": "vfy_retry"})
        job = job_queue.reserve(timeout=1)
        assert job is not None

        job_queue.fail(job, "connection reset", retryable=True)
        assert job_queue.depth() == 1
        assert job_queue.dead_letter_depth() == 0

        retried = job_queue.reserve(timeout=1)
        assert retried is not None
        assert retried.attempt == 2

    def test_deterministic_failure_goes_straight_to_dead_letter(self, job_queue: JobQueue) -> None:
        """Retrying an invalid file just burns capacity to fail identically."""
        job_queue.enqueue({"verification_public_id": "vfy_bad"})
        job = job_queue.reserve(timeout=1)
        assert job is not None

        job_queue.fail(job, "invalid media", retryable=False)
        assert job_queue.depth() == 0
        assert job_queue.dead_letter_depth() == 1

    def test_retries_are_bounded(self, job_queue: JobQueue) -> None:
        """A poison job must not loop forever."""
        job_queue.enqueue({"verification_public_id": "vfy_poison"})

        for _ in range(10):
            job = job_queue.reserve(timeout=1)
            if job is None:
                break
            job_queue.fail(job, "still failing", retryable=True)

        assert job_queue.depth() == 0
        assert job_queue.dead_letter_depth() == 1


class TestCrashRecovery:
    def test_expired_lease_is_requeued(self, job_queue: JobQueue) -> None:
        """A crashed worker's job must not be stranded.

        Without reaping, the submission would sit at QUEUED forever with no
        error and no worker owning it.
        """
        job_queue.enqueue({"verification_public_id": "vfy_crash"})
        job = job_queue.reserve(timeout=1)
        assert job is not None

        # Simulate a worker that died: rewrite the lease into the past.
        processing_key = job_queue.processing_key()
        job_queue._redis.delete(processing_key)
        job.lease_expires_at = time.time() - 10
        job_queue._redis.lpush(processing_key, job.to_json())

        assert job_queue.reap_expired() == 1
        assert job_queue.depth() == 1

        recovered = job_queue.reserve(timeout=1)
        assert recovered is not None
        assert recovered.payload["verification_public_id"] == "vfy_crash"

    def test_live_lease_is_not_reaped(self, job_queue: JobQueue) -> None:
        """A job still being worked on must be left alone."""
        job_queue.enqueue({"verification_public_id": "vfy_working"})
        job = job_queue.reserve(timeout=1)
        assert job is not None
        assert job_queue.reap_expired() == 0
        assert job_queue.depth() == 0

    def test_corrupt_entry_is_discarded(self, job_queue: JobQueue) -> None:
        job_queue._redis.lpush(job_queue.processing_key(), "not-json")
        job_queue.reap_expired()
        assert job_queue._redis.llen(job_queue.processing_key()) == 0


class TestIdempotency:
    def test_lock_prevents_duplicate_processing(self, fake_redis) -> None:  # type: ignore[no-untyped-def]
        """At-least-once delivery means a job can arrive twice."""
        guard = IdempotencyGuard(redis_client=fake_redis)
        assert guard.acquire("vfy_dup") is True
        assert guard.acquire("vfy_dup") is False

        guard.release("vfy_dup")
        assert guard.acquire("vfy_dup") is True

    def test_different_verifications_do_not_block_each_other(self, fake_redis) -> None:  # type: ignore[no-untyped-def]
        guard = IdempotencyGuard(redis_client=fake_redis)
        assert guard.acquire("vfy_a") is True
        assert guard.acquire("vfy_b") is True


class TestSerialization:
    def test_job_roundtrip(self) -> None:
        job = Job(id="abc", payload={"verification_public_id": "vfy_1"}, attempt=2)
        restored = Job.from_json(job.to_json())
        assert restored.id == job.id
        assert restored.payload == job.payload
        assert restored.attempt == 2

    def test_stats(self, job_queue: JobQueue) -> None:
        job_queue.enqueue({"verification_public_id": "vfy_1"})
        stats = job_queue.stats()
        assert stats["pending"] == 1
        assert stats["dead_letter"] == 0
