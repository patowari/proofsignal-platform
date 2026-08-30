"""Retrieval query log.

Records every query we actually issued. This is what makes "sources checked"
in a report an auditable fact rather than a claim, and it is how we keep the
product honest about coverage: we can only say we searched what is in here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import RetrievalProviderName
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.claim import Claim


class RetrievalQuery(Base, TimestampMixin):
    __tablename__ = "retrieval_queries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True
    )

    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    #: Query language. A Bangla claim generates both Bangla and English queries,
    #: because misinformation often circulates in one language while primary
    #: reporting happens in another.
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    provider: Mapped[RetrievalProviderName] = mapped_column(
        SAEnum(RetrievalProviderName, native_enum=False, length=32), nullable=False
    )

    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    #: Set when a provider failed. A failed provider lowers coverage and is
    #: disclosed in the report -- it never silently reduces the evidence base.
    error: Mapped[str | None] = mapped_column(String(255))

    claim: Mapped[Claim] = relationship(back_populates="queries")

    def __repr__(self) -> str:
        return f"<RetrievalQuery {self.provider} {self.result_count} results>"
