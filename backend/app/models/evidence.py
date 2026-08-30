"""Source, document, evidence, and cluster models.

A retrieved document is not evidence. Evidence is the specific passage relevant
to a specific claim, with a labeled relationship. We store the minimum excerpt
needed to justify a verdict -- never full article bodies. See docs/RETRIEVAL.md.
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

from app.core.enums import EvidenceRelationship, RetrievalProviderName, SourceType
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.claim import Claim


class Source(Base, TimestampMixin):
    """A publisher.

    Source type is one weighted feature among many, never a truth oracle. There
    is deliberately no per-domain trust score: see .claude/rules/verification.md.
    """

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255))

    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, native_enum=False, length=40),
        nullable=False,
        default=SourceType.UNKNOWN,
    )
    language: Mapped[str | None] = mapped_column(String(16))
    country: Mapped[str | None] = mapped_column(String(8))

    #: Claim categories for which this source is a natural primary authority
    #: (e.g. ["seismology"] for a geological survey). Raises evidence weight for
    #: matching claims only -- it does not make the source true in general.
    primary_source_categories: Mapped[list[str] | None] = mapped_column(JSONB)

    #: Whether this source is known to publish satire. Routes to the SATIRE
    #: verdict rather than FALSE: satire is not a lie, it is a genre.
    is_satirical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    documents: Mapped[list[RetrievedDocument]] = relationship(back_populates="source")

    def __repr__(self) -> str:
        return f"<Source {self.domain} {self.source_type}>"


class RetrievedDocument(Base, TimestampMixin):
    """A document we fetched while looking for evidence.

    The full body is not persisted: we keep metadata, hashes, and a bounded
    excerpt. See docs/RETRIEVAL.md on copyright.
    """

    __tablename__ = "retrieved_documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), index=True
    )

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    #: Canonical URL, the first signal for detecting syndicated duplicates.
    canonical_url: Mapped[str | None] = mapped_column(String(2048), index=True)
    title: Mapped[str | None] = mapped_column(String(1000))
    author: Mapped[str | None] = mapped_column(String(500))

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Bounded excerpt only -- enough to justify a verdict, not a republication.
    excerpt: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(16), index=True)
    word_count: Mapped[int | None] = mapped_column(Integer)

    #: Exact-duplicate detection.
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    #: Near-duplicate detection: catches reprints with small edits that a
    #: cryptographic hash treats as entirely different documents.
    simhash: Mapped[str | None] = mapped_column(String(32), index=True)

    retrieval_provider: Mapped[RetrievalProviderName | None] = mapped_column(
        SAEnum(RetrievalProviderName, native_enum=False, length=32)
    )
    fetch_status: Mapped[str | None] = mapped_column(String(32))
    fetch_error: Mapped[str | None] = mapped_column(String(255))

    #: Whether this page tried to instruct an automated reader. Reported as a
    #: property of the source; never allowed to change a verdict.
    injection_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    injection_signals: Mapped[list[str] | None] = mapped_column(JSONB)

    source: Mapped[Source | None] = relationship(back_populates="documents")
    evidence_items: Mapped[list[Evidence]] = relationship(back_populates="document")
    index_entry: Mapped[ArticleIndex | None] = relationship(
        back_populates="document", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        Index("ix_documents_dedup", "content_hash", "canonical_url"),
        Index("ix_documents_published", "published_at", "source_id"),
    )

    def __repr__(self) -> str:
        return f"<RetrievedDocument {self.id} {self.canonical_url or self.url}>"


class ArticleIndex(Base, TimestampMixin):
    """Search representation of a document.

    Separate from RetrievedDocument so re-embedding under a new model rewrites
    only index rows. The pgvector column is added by migration, since its
    dimensionality follows the configured embedding model.
    """

    __tablename__ = "article_index"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("retrieved_documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    #: Text fed to full-text search: title plus body, language-normalized.
    searchable_text: Mapped[str] = mapped_column(Text, nullable=False)
    #: Which embedding model produced the vector, so stale vectors are detectable
    #: after a model change rather than being silently compared across models.
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)

    document: Mapped[RetrievedDocument] = relationship(back_populates="index_entry")


class EvidenceCluster(Base, TimestampMixin):
    """A group of evidence items sharing one origin.

    Fifty sites reprinting one wire story is one origin, not fifty
    confirmations. Within a cluster the strongest item counts fully and the rest
    are damped -- see docs/SCORING.md.
    """

    __tablename__ = "evidence_clusters"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    verification_id: Mapped[int] = mapped_column(
        ForeignKey("verifications.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: The item chosen to represent the cluster (earliest or most authoritative).
    representative_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("retrieved_documents.id", ondelete="SET NULL")
    )
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: How members were matched: canonical_url, content_hash, simhash, embedding.
    clustering_method: Mapped[str | None] = mapped_column(String(32))
    similarity_score: Mapped[float | None] = mapped_column(Float)

    evidence_items: Mapped[list[Evidence]] = relationship(back_populates="cluster")


class Evidence(Base, TimestampMixin):
    """A claim/passage pair with a labeled relationship."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("retrieved_documents.id", ondelete="SET NULL"), index=True
    )
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), index=True
    )
    cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("evidence_clusters.id", ondelete="SET NULL"), index=True
    )

    #: The passage itself: minimum necessary to explain the verdict.
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    relationship_type: Mapped[EvidenceRelationship] = mapped_column(
        SAEnum(EvidenceRelationship, native_enum=False, length=32), nullable=False, index=True
    )

    # Scoring factors, stored individually so a weight can be explained and
    # re-derived rather than appearing as an opaque number.
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    strength_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    temporal_relevance: Mapped[float | None] = mapped_column(Float)
    directness: Mapped[float | None] = mapped_column(Float)
    source_factor: Mapped[float | None] = mapped_column(Float)
    #: Final weight after all factors, and how it was derived.
    computed_weight: Mapped[float | None] = mapped_column(Float)
    weight_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    #: Which classifier produced the label, so results stay reproducible across
    #: classifier changes.
    classifier_name: Mapped[str | None] = mapped_column(String(64))
    classifier_version: Mapped[str | None] = mapped_column(String(32))
    classifier_confidence: Mapped[float | None] = mapped_column(Float)

    claim: Mapped[Claim] = relationship(back_populates="evidence")
    document: Mapped[RetrievedDocument | None] = relationship(back_populates="evidence_items")
    cluster: Mapped[EvidenceCluster | None] = relationship(back_populates="evidence_items")

    __table_args__ = (Index("ix_evidence_claim_relationship", "claim_id", "relationship_type"),)

    def __repr__(self) -> str:
        return f"<Evidence {self.id} {self.relationship_type} w={self.computed_weight}>"
