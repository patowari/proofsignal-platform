"""Retrieval provider protocol and the shared result shape.

Every provider normalizes to `RetrievedItem` so ranking, deduplication, and
clustering do not care where a document came from.

Providers never raise on failure. A provider that cannot reach its source
returns nothing and records the reason: losing one source should narrow the
evidence base and lower coverage, not abort the verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.core.enums import RetrievalProviderName, SourceType


@dataclass(slots=True)
class RetrievedItem:
    """One candidate document, normalized across providers.

    This is a *candidate*, not evidence. Evidence is the specific passage
    relevant to a specific claim, extracted later.
    """

    url: str
    title: str
    #: Text we actually retrieved. May be a feed summary or the full article.
    text: str
    source_domain: str
    source_name: str | None = None
    source_type: SourceType = SourceType.UNKNOWN
    published_at: datetime | None = None
    language: str | None = None
    provider: RetrievalProviderName = RetrievalProviderName.INDEXED_CORPUS
    #: Canonical URL when the page declares one. First signal for detecting
    #: syndicated copies of the same report.
    canonical_url: str | None = None
    #: Retrieval score, meaning-specific to the provider. Normalized later.
    score: float = 0.0
    #: Whether this source is the natural authority for the claim at hand.
    #: Set by the provider that knows, never assumed from the domain alone.
    is_primary_source: bool = False

    @property
    def dedup_url(self) -> str:
        return self.canonical_url or self.url


@dataclass(slots=True)
class RetrievalOutcome:
    """What one provider returned, including how it failed.

    Failures are data: they lower coverage and are disclosed in the report
    rather than silently shrinking the evidence base.
    """

    provider: RetrievalProviderName
    items: list[RetrievedItem] = field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class RetrievalProvider(Protocol):
    """A source of candidate documents."""

    name: RetrievalProviderName

    def is_available(self) -> bool:
        """Whether this provider can run right now.

        Checked before use so an unavailable provider degrades the run
        explicitly instead of failing mid-pipeline.
        """
        ...

    async def search(
        self, queries: list[str], *, limit: int = 20, language: str | None = None
    ) -> RetrievalOutcome:
        """Find candidates for the given queries. Must never raise."""
        ...
