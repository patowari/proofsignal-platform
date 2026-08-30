"""Submission and media asset models.

A Submission is the anonymous public content a visitor asked us to check. There
is deliberately no user column and no raw IP: V1 has no accounts, and rate
limiting uses salted hashes in Redis instead. See docs/DATABASE.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    DateTime,
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

from app.core.enums import MediaKind, SubmissionStatus, SubmissionType
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.verification import Verification


class Submission(Base, TimestampMixin):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    #: Opaque external identifier. Serial ids are never exposed.
    public_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)

    content_type: Mapped[SubmissionType] = mapped_column(
        SAEnum(SubmissionType, native_enum=False, length=32), nullable=False
    )
    status: Mapped[SubmissionStatus] = mapped_column(
        SAEnum(SubmissionStatus, native_enum=False, length=32),
        nullable=False,
        default=SubmissionStatus.RECEIVED,
    )

    title: Mapped[str | None] = mapped_column(String(500))
    #: The submitted text, or text extracted from a URL.
    text: Mapped[str | None] = mapped_column(Text)
    #: User-supplied context for media. Verified separately from the media
    #: itself: an authentic video can carry a false caption.
    caption: Mapped[str | None] = mapped_column(Text)
    submitted_url: Mapped[str | None] = mapped_column(String(2048))
    #: URL after redirects and canonicalization.
    canonical_url: Mapped[str | None] = mapped_column(String(2048))

    detected_language: Mapped[str | None] = mapped_column(String(16), index=True)
    #: Hash of the normalized content, for dedup and caching.
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    #: Non-fatal notes from intake (truncation, extraction warnings).
    intake_notes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    media_assets: Mapped[list[MediaAsset]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", lazy="selectin"
    )
    verifications: Mapped[list[Verification]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_submissions_recent", "created_at", "status"),)

    def __repr__(self) -> str:
        return f"<Submission {self.public_id} {self.content_type}>"


class MediaAsset(Base, TimestampMixin):
    """An uploaded file.

    Binary content lives in object storage; only metadata is stored here. The
    original filename is kept as inert metadata and is never used to build a
    path -- storage keys are generated. See docs/SECURITY.md.
    """

    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    kind: Mapped[MediaKind] = mapped_column(
        SAEnum(MediaKind, native_enum=False, length=32), nullable=False
    )
    #: Generated object-storage key. Never derived from the user's filename.
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String(128), nullable=False)

    #: The type we determined from the file's own signature, not the client's claim.
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    #: Perceptual hash: survives resize and recompression, so it finds reuploads
    #: of the same image that a cryptographic hash would miss.
    perceptual_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[float | None] = mapped_column()

    #: Inert display metadata only.
    original_filename: Mapped[str | None] = mapped_column(String(255))
    #: ffprobe/EXIF output, retained for temporal analysis.
    technical_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    submission: Mapped[Submission] = relationship(back_populates="media_assets")

    def __repr__(self) -> str:
        return f"<MediaAsset {self.public_id} {self.kind}>"
