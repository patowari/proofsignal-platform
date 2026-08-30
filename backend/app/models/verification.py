"""Verification, revision, and stage models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    ConfidenceBand,
    PipelineStage,
    StageStatus,
    Verdict,
    VerificationStatus,
)
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.claim import Claim
    from app.models.media_analysis import MediaAnalysis
    from app.models.submission import Submission


class Verification(Base, TimestampMixin):
    """One verification run over a submission."""

    __tablename__ = "verifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, native_enum=False, length=32),
        nullable=False,
        default=VerificationStatus.QUEUED,
        index=True,
    )
    current_stage: Mapped[PipelineStage] = mapped_column(
        SAEnum(PipelineStage, native_enum=False, length=40),
        nullable=False,
        default=PipelineStage.QUEUED,
    )

    #: Null until scoring completes. Never set from a failure -- a technical
    #: failure yields FAILED status, not a substantive verdict.
    overall_verdict: Mapped[Verdict | None] = mapped_column(
        SAEnum(Verdict, native_enum=False, length=32), index=True
    )
    confidence_band: Mapped[ConfidenceBand | None] = mapped_column(
        SAEnum(ConfidenceBand, native_enum=False, length=16)
    )
    #: Internal numeric confidence, for debugging and future calibration. Never
    #: shown to users: see docs/SCORING.md on false precision.
    confidence_score: Mapped[float | None] = mapped_column(Float)

    summary: Mapped[str | None] = mapped_column(Text)
    #: Full scoring breakdown, so any verdict can be explained after the fact.
    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    #: True when a provider was missing or a stage degraded. Shown in the report
    #: and caps confidence at MEDIUM.
    degraded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    degradation_reasons: Mapped[list[str] | None] = mapped_column(JSONB)

    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)

    # Version stamps: what produced this result.
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(32), nullable=False)
    retrieval_version: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Model and prompt versions in force for this run.
    provider_versions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    submission: Mapped[Submission] = relationship(back_populates="verifications")
    stages: Mapped[list[VerificationStage]] = relationship(
        back_populates="verification",
        cascade="all, delete-orphan",
        order_by="VerificationStage.sequence",
        lazy="selectin",
    )
    claims: Mapped[list[Claim]] = relationship(
        back_populates="verification", cascade="all, delete-orphan"
    )
    revisions: Mapped[list[VerificationRevision]] = relationship(
        back_populates="verification",
        cascade="all, delete-orphan",
        order_by="VerificationRevision.revision_number",
    )
    media_analyses: Mapped[list[MediaAnalysis]] = relationship(
        back_populates="verification", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Drives /api/recent, which lists completed public verifications newest first.
        Index("ix_verifications_recent", "status", "created_at"),
        Index("ix_verifications_verdict_recent", "overall_verdict", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Verification {self.public_id} {self.status} {self.overall_verdict}>"


class VerificationRevision(Base, TimestampMixin):
    """An immutable snapshot of a completed run.

    Re-verifying appends a revision; prior results are never overwritten. This is
    what lets a report honestly show "this was UNVERIFIED yesterday and is
    VERIFIED today" as evidence appeared.
    """

    __tablename__ = "verification_revisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    verification_id: Mapped[int] = mapped_column(
        ForeignKey("verifications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)

    verdict: Mapped[Verdict | None] = mapped_column(SAEnum(Verdict, native_enum=False, length=32))
    confidence_band: Mapped[ConfidenceBand | None] = mapped_column(
        SAEnum(ConfidenceBand, native_enum=False, length=16)
    )
    summary: Mapped[str | None] = mapped_column(Text)
    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(32), nullable=False)
    retrieval_version: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_versions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    #: Why this re-verification ran (scheduled recheck, new evidence, manual).
    trigger: Mapped[str | None] = mapped_column(String(64))

    verification: Mapped[Verification] = relationship(back_populates="revisions")

    __table_args__ = (
        Index("uq_revision_number", "verification_id", "revision_number", unique=True),
    )


class VerificationStage(Base):
    """One pipeline stage execution.

    The progress UI reads these rows directly, which is what keeps displayed
    progress tied to real backend state rather than an animation.
    """

    __tablename__ = "verification_stages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    verification_id: Mapped[int] = mapped_column(
        ForeignKey("verifications.id", ondelete="CASCADE"), nullable=False, index=True
    )

    stage: Mapped[PipelineStage] = mapped_column(
        SAEnum(PipelineStage, native_enum=False, length=40), nullable=False
    )
    status: Mapped[StageStatus] = mapped_column(
        SAEnum(StageStatus, native_enum=False, length=32),
        nullable=False,
        default=StageStatus.PENDING,
    )
    #: Execution order, so stages sort correctly even when timestamps collide.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    error_type: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    #: Stage-specific counters (claims found, documents fetched, provider used).
    stage_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    verification: Mapped[Verification] = relationship(back_populates="stages")

    __table_args__ = (Index("uq_verification_stage", "verification_id", "stage", unique=True),)

    def __repr__(self) -> str:
        return f"<VerificationStage {self.stage} {self.status}>"
