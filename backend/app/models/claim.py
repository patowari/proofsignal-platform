"""Claim and claim entity models.

A Claim is one atomic, independently checkable assertion. We never verify a whole
article as a single blob: "a 7.8 earthquake hit Japan today killing 500" is six
separate claims, and they can have different verdicts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
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

from app.core.enums import ClaimOrigin, ClaimType, ConfidenceBand, Verdict
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.evidence import Evidence
    from app.models.retrieval import RetrievalQuery
    from app.models.verification import Verification


class Claim(Base, TimestampMixin):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    verification_id: Mapped[int] = mapped_column(
        ForeignKey("verifications.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: The claim as stated, in its original language.
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    #: Canonical restatement used for retrieval and comparison. The original is
    #: never discarded -- we do not translate away the user's content.
    normalized_claim: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")

    # Coarse predicate structure. Nullable: not every claim decomposes cleanly.
    subject: Mapped[str | None] = mapped_column(String(500))
    predicate: Mapped[str | None] = mapped_column(String(500))
    object: Mapped[str | None] = mapped_column(String(500))

    claim_type: Mapped[ClaimType] = mapped_column(
        SAEnum(ClaimType, native_enum=False, length=32), nullable=False, default=ClaimType.OTHER
    )
    #: Where the claim came from. An authentic video can carry a false caption,
    #: so transcript claims and caption claims are verified and reported apart.
    origin: Mapped[ClaimOrigin] = mapped_column(
        SAEnum(ClaimOrigin, native_enum=False, length=32),
        nullable=False,
        default=ClaimOrigin.USER_TEXT,
    )
    #: How load-bearing this claim is (0-1). Drives the overall verdict: one
    #: false central claim outweighs several true incidental ones.
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    #: Position in the source content, for stable display ordering.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Extracted values, stored parsed so numeric and temporal comparison work on
    # values rather than strings. "$50 billion" vs "$5 billion" must be
    # comparable as magnitudes.
    dates: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    numbers: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    money: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    percentages: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    locations: Mapped[list[str] | None] = mapped_column(JSONB)

    verdict: Mapped[Verdict | None] = mapped_column(
        SAEnum(Verdict, native_enum=False, length=32), index=True
    )
    confidence_band: Mapped[ConfidenceBand | None] = mapped_column(
        SAEnum(ConfidenceBand, native_enum=False, length=16)
    )
    #: Support, contradiction, coverage, penalties, and the matched decision
    #: rule. Every claim verdict must be explainable from this.
    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    verification: Mapped[Verification] = relationship(back_populates="claims")
    entities: Mapped[list[ClaimEntity]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", lazy="selectin"
    )
    evidence: Mapped[list[Evidence]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )
    queries: Mapped[list[RetrievalQuery]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_claims_verification_sequence", "verification_id", "sequence"),)

    def __repr__(self) -> str:
        return f"<Claim {self.id} {self.claim_type} {self.verdict}>"


class ClaimEntity(Base):
    """A normalized entity mentioned in a claim.

    Used for entity-overlap ranking during retrieval and for entity-mismatch
    penalties during scoring: the right event attributed to the wrong actor is a
    common misinformation pattern.
    """

    __tablename__ = "claim_entities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: Surface form as written in the claim.
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    #: Canonical form, so "US"/"U.S."/"United States" match each other.
    normalized: Mapped[str | None] = mapped_column(String(500), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)

    claim: Mapped[Claim] = relationship(back_populates="entities")

    def __repr__(self) -> str:
        return f"<ClaimEntity {self.text!r} {self.entity_type}>"
