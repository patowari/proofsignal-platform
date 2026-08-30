"""Verification pipeline.

A real state machine. Each stage writes a VerificationStage row before and after
it runs, which is what lets the progress UI show actual backend state rather
than an animation.

Two rules govern failure handling, and both matter to the product:

1. A technical failure is never a verdict. If we could not check something, the
   result is FAILED or UNVERIFIED with a stated reason -- never FALSE.
2. A missing optional capability degrades the run and is disclosed, rather than
   silently producing a thinner result that looks complete.

See docs/VERIFICATION_PIPELINE.md.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    PipelineStage,
    StageStatus,
    SubmissionStatus,
    VerificationStatus,
)
from app.core.errors import AppError, StageFailedError
from app.core.logging import get_logger
from app.models import Submission, Verification, VerificationStage

logger = get_logger(__name__)

#: Execution order. ANALYZING_MEDIA is skipped when there is no media.
STAGE_SEQUENCE: tuple[PipelineStage, ...] = (
    PipelineStage.NORMALIZING,
    PipelineStage.EXTRACTING_CONTENT,
    PipelineStage.DETECTING_LANGUAGE,
    PipelineStage.EXTRACTING_CLAIMS,
    PipelineStage.GENERATING_QUERIES,
    PipelineStage.RETRIEVING_EVIDENCE,
    PipelineStage.FETCHING_DOCUMENTS,
    PipelineStage.EXTRACTING_EVIDENCE,
    PipelineStage.CLASSIFYING_EVIDENCE,
    PipelineStage.ANALYZING_MEDIA,
    PipelineStage.SCORING,
    PipelineStage.GENERATING_REPORT,
)

#: Stages whose failure ends the run. Everything else degrades and continues:
#: losing one retrieval provider should narrow the evidence base, not abort.
FATAL_STAGES: frozenset[PipelineStage] = frozenset(
    {
        PipelineStage.NORMALIZING,
        PipelineStage.EXTRACTING_CLAIMS,
        PipelineStage.SCORING,
        PipelineStage.GENERATING_REPORT,
    }
)


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class PipelineContext:
    """Mutable state carried between stages.

    Stages communicate through this rather than by re-reading the database, so
    each stage's inputs are explicit and the whole run is testable in isolation.
    """

    verification: Verification
    submission: Submission
    session: Session

    #: Text to analyze, keyed by ClaimOrigin. Origins stay separate because an
    #: authentic video can carry a false caption.
    text_by_origin: dict[str, str] = field(default_factory=dict)
    language: str = "en"
    claims: list[Any] = field(default_factory=list)
    queries: list[Any] = field(default_factory=list)
    retrieved_documents: list[Any] = field(default_factory=list)
    evidence: list[Any] = field(default_factory=list)
    media_analyses: list[Any] = field(default_factory=list)

    degraded: bool = False
    degradation_reasons: list[str] = field(default_factory=list)

    def degrade(self, reason: str) -> None:
        """Record a capability we could not use.

        Surfaced in the report and caps confidence at MEDIUM: a run that did not
        look everywhere must not claim certainty.
        """
        if reason not in self.degradation_reasons:
            self.degradation_reasons.append(reason)
        self.degraded = True
        logger.info("pipeline.degraded", reason=reason)


#: A stage function: takes the context, returns metadata for its stage row.
StageFunc = Callable[[PipelineContext], dict[str, Any]]


class VerificationPipeline:
    """Runs a verification through its stages, persisting every transition."""

    def __init__(self, stages: dict[PipelineStage, StageFunc] | None = None) -> None:
        #: Injectable so tests can substitute stage implementations. Production
        #: wiring lives in app/verification/stages.py.
        self._stages = stages or {}

    def register(self, stage: PipelineStage, func: StageFunc) -> None:
        self._stages[stage] = func

    # ---- Stage row bookkeeping -----------------------------------------

    def _get_or_create_stage_row(
        self, session: Session, verification: Verification, stage: PipelineStage, sequence: int
    ) -> VerificationStage:
        row = session.execute(
            select(VerificationStage).where(
                VerificationStage.verification_id == verification.id,
                VerificationStage.stage == stage,
            )
        ).scalar_one_or_none()

        if row is None:
            row = VerificationStage(
                verification_id=verification.id,
                stage=stage,
                status=StageStatus.PENDING,
                sequence=sequence,
            )
            session.add(row)
            session.flush()
        return row

    def _completed_stages(self, session: Session, verification: Verification) -> set[PipelineStage]:
        """Stages already finished, so a redelivered job resumes rather than repeats."""
        rows = session.execute(
            select(VerificationStage.stage).where(
                VerificationStage.verification_id == verification.id,
                VerificationStage.status.in_(
                    [StageStatus.COMPLETED, StageStatus.SKIPPED, StageStatus.DEGRADED]
                ),
            )
        ).scalars()
        return set(rows)

    # ---- Execution ------------------------------------------------------

    def run(self, context: PipelineContext) -> Verification:
        """Execute the pipeline. Returns the updated verification."""
        verification = context.verification
        session = context.session

        verification.status = VerificationStatus.RUNNING
        verification.started_at = verification.started_at or utcnow()
        context.submission.status = SubmissionStatus.PROCESSING
        session.flush()

        already_done = self._completed_stages(session, verification)
        if already_done:
            logger.info(
                "pipeline.resuming",
                verification_id=verification.public_id,
                completed=len(already_done),
            )

        applicable = self._applicable_stages(context)

        for sequence, stage in enumerate(applicable, start=1):
            if stage in already_done:
                continue

            row = self._get_or_create_stage_row(session, verification, stage, sequence)
            verification.current_stage = stage
            row.status = StageStatus.RUNNING
            row.started_at = utcnow()
            session.flush()
            session.commit()  # publish progress so pollers see it immediately

            started = time.monotonic()
            try:
                handler = self._stages.get(stage)
                if handler is None:
                    # No implementation yet. Recorded honestly as skipped with a
                    # reason -- never quietly treated as a completed stage.
                    row.status = StageStatus.SKIPPED
                    row.stage_metadata = {"reason": "stage_not_implemented"}
                    context.degrade(f"{stage.value.lower()}_not_implemented")
                else:
                    metadata = handler(context) or {}
                    row.stage_metadata = metadata
                    row.status = (
                        StageStatus.DEGRADED if metadata.get("degraded") else StageStatus.COMPLETED
                    )

                row.finished_at = utcnow()
                row.duration_ms = int((time.monotonic() - started) * 1000)
                session.flush()
                session.commit()

            except Exception as exc:
                row.status = StageStatus.FAILED
                row.finished_at = utcnow()
                row.duration_ms = int((time.monotonic() - started) * 1000)
                row.error_type = type(exc).__name__
                row.error_message = str(exc)[:2000]
                session.flush()

                logger.error(
                    "pipeline.stage_failed",
                    verification_id=verification.public_id,
                    stage=stage.value,
                    error_type=type(exc).__name__,
                    error=str(exc)[:500],
                )

                if stage in FATAL_STAGES:
                    return self._fail(context, stage, exc)

                # Non-fatal: note it and carry on with less evidence.
                context.degrade(f"{stage.value.lower()}_failed")
                session.commit()

        return self._complete(context)

    def _applicable_stages(self, context: PipelineContext) -> list[PipelineStage]:
        """Stages that apply to this submission.

        Media analysis is omitted entirely when there is no media, so the
        progress UI never shows a step that will not run.
        """
        has_media = bool(context.submission.media_assets)
        return [s for s in STAGE_SEQUENCE if s is not PipelineStage.ANALYZING_MEDIA or has_media]

    def _complete(self, context: PipelineContext) -> Verification:
        verification = context.verification
        verification.status = VerificationStatus.COMPLETED
        verification.current_stage = PipelineStage.COMPLETED
        verification.completed_at = utcnow()
        verification.degraded = context.degraded
        verification.degradation_reasons = context.degradation_reasons or None
        context.submission.status = SubmissionStatus.COMPLETED

        context.session.flush()
        context.session.commit()

        logger.info(
            "pipeline.completed",
            verification_id=verification.public_id,
            verdict=verification.overall_verdict.value if verification.overall_verdict else None,
            degraded=context.degraded,
        )
        return verification

    def _fail(self, context: PipelineContext, stage: PipelineStage, exc: Exception) -> Verification:
        """Record a terminal failure.

        Deliberately leaves overall_verdict as None. A processing failure is not
        evidence about the claim, and must never be rendered as one.
        """
        verification = context.verification
        verification.status = VerificationStatus.FAILED
        verification.current_stage = PipelineStage.FAILED
        verification.completed_at = utcnow()
        verification.error_code = exc.code if isinstance(exc, AppError) else type(exc).__name__
        verification.error_message = str(exc)[:2000]
        verification.degraded = context.degraded
        verification.degradation_reasons = context.degradation_reasons or None
        verification.overall_verdict = None
        context.submission.status = SubmissionStatus.FAILED

        context.session.flush()
        context.session.commit()

        logger.error(
            "pipeline.failed",
            verification_id=verification.public_id,
            stage=stage.value,
            error_code=verification.error_code,
        )
        return verification


def is_transient_failure(exc: Exception) -> bool:
    """Whether the queue should retry.

    Transient (network, provider timeout) is worth retrying; deterministic
    (invalid media, malformed input) will fail identically every time.
    """
    if isinstance(exc, AppError):
        return exc.transient
    return isinstance(exc, TimeoutError | ConnectionError | OSError)


__all__ = [
    "FATAL_STAGES",
    "STAGE_SEQUENCE",
    "PipelineContext",
    "StageFailedError",
    "VerificationPipeline",
    "is_transient_failure",
]
