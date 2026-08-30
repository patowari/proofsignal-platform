"""Media analysis and transcript models.

The governing rule: media *integrity* (was the file manipulated?) is stored and
reported separately from claim *context* (does it show what the caption says?).
An authentic photo with a false caption is the most common misinformation
pattern, and collapsing both into one score destroys it.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AnalysisAvailability, MediaKind
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.verification import Verification


class MediaAnalysis(Base, TimestampMixin):
    __tablename__ = "media_analyses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    verification_id: Mapped[int] = mapped_column(
        ForeignKey("verifications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_asset_id: Mapped[int] = mapped_column(
        ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[MediaKind] = mapped_column(
        SAEnum(MediaKind, native_enum=False, length=32), nullable=False
    )

    # ---- Integrity signals ------------------------------------------------
    #: EXIF and container metadata. An editing tool in the software field is a
    #: signal worth reporting, not proof of forgery -- most images are edited.
    metadata_findings: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    #: Heuristic manipulation indicators, each with what triggered it.
    manipulation_signals: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    #: Capture time from metadata, when present and plausible.
    metadata_captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ---- Context signals --------------------------------------------------
    #: Matches in our own indexed corpus. We do not have reverse image search;
    #: an empty result means "not in our corpus", never "not on the internet".
    corpus_matches: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    #: Earliest appearance we can evidence. Null when unknown -- and unknown is
    #: reported as unknown, never guessed.
    earliest_known_appearance: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: True when the media demonstrably predates the claimed event: the
    #: recycled-image case.
    predates_claimed_event: Mapped[bool | None] = mapped_column(Boolean)

    # ---- OCR --------------------------------------------------------------
    ocr_status: Mapped[AnalysisAvailability] = mapped_column(
        SAEnum(AnalysisAvailability, native_enum=False, length=32),
        nullable=False,
        default=AnalysisAvailability.SKIPPED,
    )
    ocr_text: Mapped[str | None] = mapped_column(Text)
    ocr_engine: Mapped[str | None] = mapped_column(String(64))
    #: Why OCR did not run. Prevents "no engine installed" from being read as
    #: "no text in the image".
    ocr_unavailable_reason: Mapped[str | None] = mapped_column(String(255))

    # ---- Screenshot-specific ---------------------------------------------
    #: Fields read off a screenshot: account name, handle, timestamp, counts.
    #: A screenshot proves an image exists, not that the depicted post is real.
    screenshot_fields: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # ---- Video-specific ---------------------------------------------------
    keyframe_count: Mapped[int | None] = mapped_column(Integer)
    keyframes: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    scene_change_count: Mapped[int | None] = mapped_column(Integer)

    # ---- Availability -----------------------------------------------------
    #: Per-sub-analysis status, so the report can distinguish "we checked and
    #: found nothing" from "we could not check".
    analysis_availability: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    processing_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)

    verification: Mapped[Verification] = relationship(back_populates="media_analyses")

    def __repr__(self) -> str:
        return f"<MediaAnalysis {self.id} {self.kind}>"


class VideoTranscript(Base, TimestampMixin):
    """Speech-to-text output for a video."""

    __tablename__ = "video_transcripts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    media_asset_id: Mapped[int] = mapped_column(
        ForeignKey("media_assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    status: Mapped[AnalysisAvailability] = mapped_column(
        SAEnum(AnalysisAvailability, native_enum=False, length=32),
        nullable=False,
        default=AnalysisAvailability.SKIPPED,
    )
    text: Mapped[str | None] = mapped_column(Text)
    #: Timestamped segments, so a transcript claim can be traced to a moment in
    #: the video rather than asserted about the whole file.
    segments: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    language: Mapped[str | None] = mapped_column(String(16))
    language_confidence: Mapped[float | None] = mapped_column(Float)

    model_name: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(32))
    duration_processed_seconds: Mapped[float | None] = mapped_column(Float)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unavailable_reason: Mapped[str | None] = mapped_column(String(255))

    def __repr__(self) -> str:
        return f"<VideoTranscript {self.id} {self.status}>"
