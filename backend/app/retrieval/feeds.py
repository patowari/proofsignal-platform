"""RSS/Atom feed retrieval.

Fetches configured news feeds and scores their entries against a claim's
queries. This is the provider that makes the product actually check something:
without it every verification is honestly UNVERIFIED because nothing is searched.

Feeds are fetched concurrently with a per-feed timeout and cached briefly, so a
single slow or broken publisher cannot stall a verification.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anyio
import httpx
import yaml

from app.core.config import get_settings
from app.core.enums import RetrievalProviderName, SourceType
from app.core.logging import get_logger
from app.retrieval.base import RetrievalOutcome, RetrievedItem
from app.retrieval.scoring import score_against_queries

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FeedConfig:
    name: str
    url: str
    domain: str
    language: str
    country: str
    category: str
    source_type: SourceType
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class PrimarySource:
    domain: str
    name: str
    source_type: SourceType


def _resolve_config_path() -> Path:
    """Locate feeds.yaml relative to the backend package.

    Resolved from this file rather than the working directory, so the worker
    and the API find the same file however they were launched.
    """
    configured = Path(get_settings().feeds_config_path)
    if configured.is_absolute() and configured.exists():
        return configured

    backend_root = Path(__file__).resolve().parents[2]
    candidates = [
        backend_root / configured,
        backend_root.parent / "infrastructure" / "feeds.yaml",
        Path.cwd() / configured,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return (backend_root.parent / "infrastructure" / "feeds.yaml").resolve()


_config_cache: dict[str, Any] | None = None


def load_feed_config() -> dict[str, Any]:
    """Load and cache feeds.yaml.

    A malformed or missing config disables feed retrieval rather than crashing
    the worker: the run degrades and says so.
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    path = _resolve_config_path()
    try:
        with path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.error("feeds.config_unreadable", path=str(path), error=str(exc))
        _config_cache = {"feeds": [], "primary_sources": {}}
        return _config_cache

    feeds: list[FeedConfig] = []
    for entry in raw.get("feeds", []):
        try:
            feeds.append(
                FeedConfig(
                    name=entry["name"],
                    url=entry["url"],
                    domain=entry["domain"],
                    language=entry.get("language", "en"),
                    country=entry.get("country", ""),
                    category=entry.get("category", "general"),
                    source_type=SourceType(entry.get("source_type", "UNKNOWN")),
                    enabled=entry.get("enabled", True),
                )
            )
        except (KeyError, ValueError) as exc:
            # Skip the bad entry, keep the rest: one typo should not disable
            # every source.
            logger.warning("feeds.bad_entry", entry=str(entry)[:120], error=str(exc))

    primary: dict[str, list[PrimarySource]] = {}
    for category, sources in (raw.get("primary_sources") or {}).items():
        parsed = []
        for source in sources:
            try:
                parsed.append(
                    PrimarySource(
                        domain=source["domain"],
                        name=source.get("name", source["domain"]),
                        source_type=SourceType(source.get("source_type", "UNKNOWN")),
                    )
                )
            except (KeyError, ValueError):
                continue
        primary[category] = parsed

    _config_cache = {"feeds": feeds, "primary_sources": primary}
    logger.info(
        "feeds.config_loaded",
        path=str(path),
        feed_count=len(feeds),
        enabled=sum(1 for f in feeds if f.enabled),
    )
    return _config_cache


def enabled_feeds(language: str | None = None) -> list[FeedConfig]:
    """Enabled feeds, optionally prioritized for a language.

    Other languages are kept rather than filtered out: a Bangla claim is often
    corroborated or contradicted by English reporting, and vice versa. They are
    simply ordered after the matching-language feeds.
    """
    feeds = [f for f in load_feed_config()["feeds"] if f.enabled]
    if language:
        matching = [f for f in feeds if f.language == language]
        other = [f for f in feeds if f.language != language]
        return matching + other
    return feeds


def primary_sources_for(category: str) -> list[PrimarySource]:
    return load_feed_config()["primary_sources"].get(category, [])


def is_primary_source_domain(domain: str) -> bool:
    """Whether a domain is a registered primary source for any claim category."""
    domain = domain.lower().removeprefix("www.")
    for sources in load_feed_config()["primary_sources"].values():
        if any(domain == s.domain or domain.endswith("." + s.domain) for s in sources):
            return True
    return False


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

#: Parsed feed entries, keyed by feed URL, with the time they were fetched.
#: News feeds update on the order of minutes; refetching every one on every
#: verification would be slow and rude to publishers.
_entry_cache: dict[str, tuple[float, list[RetrievedItem]]] = {}
_CACHE_TTL_SECONDS = 600


def _parse_entry_date(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, key, None) or (entry.get(key) if isinstance(entry, dict) else None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=UTC)
            except (TypeError, ValueError):
                continue
    return None


def _clean_html(text: str) -> str:
    """Strip markup from a feed summary.

    Feed summaries routinely contain HTML. It is untrusted content, so it is
    stripped rather than rendered anywhere.
    """
    if not text:
        return ""
    try:
        from bs4 import BeautifulSoup

        return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    except Exception:
        import re

        return re.sub(r"<[^>]+>", " ", text).strip()


def _parse_feed(content: bytes, feed: FeedConfig) -> list[RetrievedItem]:
    """Parse feed bytes into normalized items."""
    import feedparser

    parsed = feedparser.parse(content)
    items: list[RetrievedItem] = []

    for entry in parsed.entries[:60]:
        link = getattr(entry, "link", None)
        title = getattr(entry, "title", None)
        if not link or not title:
            continue

        summary = _clean_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))
        # Some feeds put the body in content[] instead of summary.
        if not summary:
            content_list = getattr(entry, "content", None) or []
            if content_list:
                summary = _clean_html(content_list[0].get("value", ""))

        items.append(
            RetrievedItem(
                url=link,
                title=_clean_html(title),
                text=summary,
                source_domain=feed.domain,
                source_name=feed.name,
                source_type=feed.source_type,
                published_at=_parse_entry_date(entry),
                language=feed.language,
                provider=RetrievalProviderName.RSS_CORPUS,
            )
        )
    return items


async def _fetch_feed(client: httpx.AsyncClient, feed: FeedConfig) -> list[RetrievedItem]:
    """Fetch and parse one feed. Returns [] on any failure.

    Feed URLs come from our own configuration, not from users, so they do not
    go through the SSRF layer -- that guards user-influenced URLs. Article URLs
    discovered *in* feeds do go through safe_fetch when we fetch their bodies.
    """
    cached = _entry_cache.get(feed.url)
    if cached and time.time() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    try:
        response = await client.get(feed.url, follow_redirects=True)
        if response.status_code != 200:
            logger.warning("feeds.fetch_failed", feed=feed.name, status=response.status_code)
            return []
        items = await anyio.to_thread.run_sync(_parse_feed, response.content, feed)
    except (httpx.HTTPError, Exception) as exc:
        logger.warning("feeds.fetch_error", feed=feed.name, error_type=type(exc).__name__)
        return []

    _entry_cache[feed.url] = (time.time(), items)
    logger.info("feeds.fetched", feed=feed.name, entries=len(items))
    return items


class RSSFeedProvider:
    """Retrieval over configured news feeds."""

    name = RetrievalProviderName.RSS_CORPUS

    def is_available(self) -> bool:
        settings = get_settings()
        return settings.rss_enabled and bool(enabled_feeds())

    async def search(
        self, queries: list[str], *, limit: int = 20, language: str | None = None
    ) -> RetrievalOutcome:
        started = time.monotonic()
        settings = get_settings()

        if not self.is_available():
            return RetrievalOutcome(provider=self.name, error="rss_disabled_or_no_feeds")
        if not queries:
            return RetrievalOutcome(provider=self.name, error="no_queries")

        feeds = enabled_feeds(language)[: settings.rss_max_feeds_per_query]

        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": settings.user_agent},
                follow_redirects=True,
                timeout=settings.rss_feed_timeout_seconds,
            ) as client:
                # Concurrent, so one slow publisher does not serialize the rest.
                results = await asyncio.gather(
                    *(_fetch_feed(client, feed) for feed in feeds),
                    return_exceptions=True,
                )
        except Exception as exc:
            return RetrievalOutcome(
                provider=self.name,
                duration_ms=int((time.monotonic() - started) * 1000),
                error=f"fetch_failed:{type(exc).__name__}",
            )

        candidates: list[RetrievedItem] = []
        for result in results:
            if isinstance(result, list):
                candidates.extend(result)

        if not candidates:
            return RetrievalOutcome(
                provider=self.name,
                duration_ms=int((time.monotonic() - started) * 1000),
                error="no_entries_retrieved",
            )

        # Score title and body separately, then combine with the title
        # dominant. A headline states the article's actual subject, whereas a
        # feed summary often carries boilerplate, related-story teasers, and
        # section labels that produce confident-looking false matches. Requiring
        # the title to carry most of the signal is what keeps an article about a
        # campus mosque from matching a claim about teacher transfers.
        scored: list[RetrievedItem] = []
        for item in candidates:
            title_score = score_against_queries(item.title, queries, language=item.language)
            body_score = score_against_queries(item.text, queries, language=item.language)
            item.score = min(1.0, title_score * 0.75 + body_score * 0.25)

            # A body-only match is topical drift, not relevance. Require the
            # headline to show some connection before the article counts.
            if title_score < 0.12:
                continue
            if item.score > 0:
                scored.append(item)

        scored.sort(key=lambda i: i.score, reverse=True)

        logger.info(
            "feeds.search_complete",
            candidates=len(candidates),
            matched=len(scored),
            returned=min(limit, len(scored)),
        )

        return RetrievalOutcome(
            provider=self.name,
            items=scored[:limit],
            duration_ms=int((time.monotonic() - started) * 1000),
        )


def clear_caches() -> None:
    """Reset cached config and entries. Used by tests."""
    global _config_cache
    _config_cache = None
    _entry_cache.clear()
