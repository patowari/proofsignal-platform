"""Verification worker.

Consumes jobs and runs the pipeline. Run with:

    python -m app.workers.worker

Idempotent by construction: at-least-once delivery means a job can arrive twice,
so a lock prevents concurrent duplicate processing and the pipeline resumes from
the last completed stage rather than repeating finished work.
"""

from __future__ import annotations

# Must precede any event-loop or database import: psycopg's async mode cannot
# drive Windows' default ProactorEventLoop.
from app.core.runtime import configure_event_loop

configure_event_loop()

import signal
import sys
import time
from types import FrameType

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import configure_logging, get_logger, verification_id_var
from app.db.session import get_sync_session_factory
from app.models import Submission, Verification
from app.verification.pipeline import (
    PipelineContext,
    VerificationPipeline,
    is_transient_failure,
)
from app.verification.stages import DEFAULT_STAGES
from app.workers.queue import IdempotencyGuard, Job, JobQueue

logger = get_logger(__name__)

_shutdown = False


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    """Finish the job in hand, then stop.

    Killing a worker mid-verification would leave the submission stuck until the
    reaper timed it out, so shutdown is cooperative.
    """
    global _shutdown
    _shutdown = True
    logger.info("worker.shutdown_requested", signal=signum)


def process_job(job: Job, session: Session, pipeline: VerificationPipeline) -> None:
    """Run one verification job."""
    verification_public_id = job.payload.get("verification_public_id")
    if not verification_public_id:
        raise ValueError("job payload has no verification_public_id")

    verification_id_var.set(verification_public_id)

    verification = session.execute(
        select(Verification).where(Verification.public_id == verification_public_id)
    ).scalar_one_or_none()

    if verification is None:
        # Nothing to retry: the record is gone.
        logger.error("worker.verification_missing", verification_id=verification_public_id)
        return

    submission = session.execute(
        select(Submission).where(Submission.id == verification.submission_id)
    ).scalar_one()

    context = PipelineContext(verification=verification, submission=submission, session=session)
    pipeline.run(context)


def run_worker(max_jobs: int | None = None, poll_timeout: int = 5) -> int:
    """Main worker loop.

    Args:
        max_jobs: Stop after this many jobs. Used by tests; None runs forever.
        poll_timeout: Seconds to block waiting for a job.

    Returns the number of jobs processed.
    """
    configure_logging()

    queue = JobQueue()
    guard = IdempotencyGuard()
    pipeline = VerificationPipeline(dict(DEFAULT_STAGES))
    session_factory = get_sync_session_factory()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info(
        "worker.started",
        queue=queue.name,
        consumer=queue.consumer_id,
        max_jobs=max_jobs,
    )

    processed = 0
    last_reap = time.monotonic()

    while not _shutdown:
        if max_jobs is not None and processed >= max_jobs:
            break

        # Periodically return jobs abandoned by crashed workers.
        if time.monotonic() - last_reap > 60:
            requeued = queue.reap_expired()
            if requeued:
                logger.info("worker.reaped_jobs", count=requeued)
            last_reap = time.monotonic()

        job = queue.reserve(timeout=poll_timeout)
        if job is None:
            continue

        verification_public_id = job.payload.get("verification_public_id", "")

        # Another worker may already hold this verification.
        if not guard.acquire(verification_public_id):
            logger.info("worker.already_processing", verification_id=verification_public_id)
            queue.complete(job)
            continue

        started = time.monotonic()
        try:
            with session_factory() as session:
                process_job(job, session, pipeline)
            queue.complete(job)
            processed += 1
            logger.info(
                "worker.job_completed",
                job_id=job.id,
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        except Exception as exc:
            # The pipeline records its own failure state; the queue decides
            # only whether another attempt could plausibly succeed.
            retryable = is_transient_failure(exc)
            queue.fail(job, f"{type(exc).__name__}: {exc}", retryable=retryable)
            logger.error(
                "worker.job_failed",
                job_id=job.id,
                error_type=type(exc).__name__,
                retryable=retryable,
                error=str(exc)[:500],
            )
        finally:
            guard.release(verification_public_id)
            verification_id_var.set(None)

    logger.info("worker.stopped", processed=processed)
    queue.close()
    return processed


def main() -> int:
    try:
        run_worker()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        logger.error("worker.fatal", error_type=type(exc).__name__, error=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
