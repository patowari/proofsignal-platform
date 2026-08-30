"""Article body extraction.

A feed summary is often one sentence. To judge whether a source supports or
contradicts a claim we usually need the article body, which means fetching the
page -- through the SSRF-safe fetcher, because these URLs come from feeds and
from users, not from us.

Copyright: we keep only the excerpt needed to justify a verdict, never the full
body. See docs/RETRIEVAL.md.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

import anyio

from app.ai.untrusted import detect_injection_signals
from app.core.errors import FetchError, UnsafeURLError
from app.core.logging import get_logger
from app.security.safe_fetch import safe_fetch

logger = get_logger(__name__)

#: Cap on stored body text. Enough to locate relevant passages without
#: retaining a redistributable copy of the article.
MAX_BODY_CHARS = 12_000


@dataclass(slots=True)
class ExtractedArticle:
    url: str
    canonical_url: str | None
    title: str | None
    text: str
    author: str | None = None
    published_at: datetime | None = None
    language: str | None = None
    content_hash: str | None = None
    #: True when the page contains text trying to instruct an automated reader.
    #: Reported as a property of the source; it never affects a verdict.
    injection_detected: bool = False
    injection_signals: tuple[str, ...] = ()


def _extract_with_trafilatura(html: str, url: str) -> dict[str, object] | None:
    """Extract the main article body.

    Trafilatura strips navigation, ads, and comment sections, which otherwise
    dominate a naive text extraction and produce spurious keyword matches.
    """
    try:
        import trafilatura
        from trafilatura.settings import use_config

        config = use_config()
        # Bound extraction time: some pages are pathological.
        config.set("DEFAULT", "EXTRACTION_TIMEOUT", "10")

        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
            config=config,
        )
        if not text:
            return None

        metadata = trafilatura.extract_metadata(html)
        return {
            "text": text,
            "title": getattr(metadata, "title", None) if metadata else None,
            "author": getattr(metadata, "author", None) if metadata else None,
            "date": getattr(metadata, "date", None) if metadata else None,
            "canonical": getattr(metadata, "url", None) if metadata else None,
        }
    except Exception as exc:
        logger.debug("article.trafilatura_failed", error_type=type(exc).__name__)
        return None


def _extract_with_soup(html: str) -> dict[str, object] | None:
    """Fallback extraction when Trafilatura finds nothing."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()

        title = None
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        canonical = None
        link = soup.find("link", rel="canonical")
        if link and link.get("href"):
            canonical = link["href"]

        # Paragraph text only: this skips most chrome without a full parser.
        paragraphs = [
            p.get_text(" ", strip=True)
            for p in soup.find_all("p")
            if len(p.get_text(strip=True)) > 40
        ]
        text = "\n\n".join(paragraphs)
        if not text:
            return None

        return {"text": text, "title": title, "author": None, "date": None, "canonical": canonical}
    except Exception:
        return None


def _parse_date(value: object) -> datetime | None:
    if not value:
        return None
    try:
        from dateutil import parser

        parsed = parser.parse(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except Exception:
        return None


async def fetch_article(url: str) -> ExtractedArticle | None:
    """Fetch and extract one article. Returns None on any failure.

    Never raises: one unreachable source should narrow the evidence base, not
    fail the verification.
    """
    try:
        result = await safe_fetch(url)
    except (UnsafeURLError, FetchError) as exc:
        logger.info("article.fetch_skipped", url_host=url[:80], reason=type(exc).__name__)
        return None
    except Exception as exc:
        logger.warning("article.fetch_error", error_type=type(exc).__name__)
        return None

    if not result.ok or not result.text:
        return None

    # Extraction is CPU-bound HTML parsing; keep it off the event loop.
    extracted = await anyio.to_thread.run_sync(
        _extract_with_trafilatura, result.text, result.final_url
    )
    if not extracted:
        extracted = await anyio.to_thread.run_sync(_extract_with_soup, result.text)
    if not extracted:
        logger.info("article.no_content_extracted", url_host=url[:80])
        return None

    text = str(extracted["text"])[:MAX_BODY_CHARS]

    # The page is untrusted content. We record manipulation attempts as a
    # property of the source rather than acting on them.
    signals = detect_injection_signals(text)

    return ExtractedArticle(
        url=result.final_url,
        canonical_url=str(extracted.get("canonical") or "") or None,
        title=str(extracted.get("title") or "") or None,
        text=text,
        author=str(extracted.get("author") or "") or None,
        published_at=_parse_date(extracted.get("date")),
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
        injection_detected=bool(signals),
        injection_signals=signals,
    )
