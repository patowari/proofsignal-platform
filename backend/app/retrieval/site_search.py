"""Site search: retrieval beyond the RSS window.

RSS feeds carry only a publisher's most recent items -- typically 20-60 -- and
section stories often never appear in the main feed at all. A story can be live
on prothomalo.com and absent from every feed we poll, which produced UNVERIFIED
results for claims the publisher had plainly reported.

This provider closes that gap by using each publisher's own on-site search,
which indexes their whole archive.

What this is not: we do not scrape Google, Bing, or any search engine, and we do
not bypass access controls. These are the publishers' own public search pages,
fetched through the SSRF-safe fetcher and rate-limited by a per-verification cap.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from urllib.parse import quote, urljoin

import anyio
import httpx

from app.core.config import get_settings
from app.core.enums import RetrievalProviderName, SourceType
from app.core.logging import get_logger
from app.retrieval.base import RetrievalOutcome, RetrievedItem
from app.retrieval.scoring import score_against_queries, tokenize

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SearchableSite:
    """A publisher whose on-site search we can query."""

    name: str
    domain: str
    #: Query URL with {q} where the URL-encoded search terms go.
    search_url: str
    language: str
    source_type: SourceType = SourceType.NEWS_ORGANIZATION
    #: Path fragment that marks a link as an article rather than navigation.
    article_pattern: str = ""


#: Publishers with a working public search endpoint. Verified live; a site whose
#: search breaks simply returns nothing rather than failing the verification.
SEARCHABLE_SITES: tuple[SearchableSite, ...] = (
    SearchableSite(
        name="Prothom Alo",
        domain="prothomalo.com",
        search_url="https://www.prothomalo.com/search?q={q}",
        language="bn",
    ),
    SearchableSite(
        name="Jagonews24",
        domain="jagonews24.com",
        search_url="https://www.jagonews24.com/search?q={q}",
        language="bn",
    ),
    SearchableSite(
        name="Samakal",
        domain="samakal.com",
        search_url="https://samakal.com/search?q={q}",
        language="bn",
    ),
    SearchableSite(
        name="The Daily Star",
        domain="thedailystar.net",
        search_url="https://www.thedailystar.net/search?search={q}",
        language="en",
    ),
    SearchableSite(
        name="Dhaka Tribune",
        domain="dhakatribune.com",
        search_url="https://www.dhakatribune.com/search?q={q}",
        language="en",
    ),
)

#: Link text shorter than this is navigation, not a headline.
_MIN_HEADLINE_CHARS = 20

#: Paths that are navigation rather than articles.
_NON_ARTICLE = re.compile(
    r"/(search|tag|topic|author|category|page|login|subscribe|privacy|terms|about)(/|$|\?)",
    re.I,
)


def _build_query(claim_text: str, *, language: str, max_terms: int = 6) -> str:
    """Build a search string from a claim.

    Site search engines behave poorly with a whole sentence, so the most
    discriminating terms are used instead. Longest-first because in Bengali the
    longer tokens carry the subject.
    """
    tokens = tokenize(claim_text, language=language)
    if not tokens:
        return claim_text[:80]

    seen: set[str] = set()
    ordered: list[str] = []
    for token in sorted(tokens, key=len, reverse=True):
        if token not in seen and len(token) >= 4:
            seen.add(token)
            ordered.append(token)
        if len(ordered) >= max_terms:
            break

    return " ".join(ordered) or claim_text[:80]


def _extract_results(html: str, site: SearchableSite) -> list[tuple[str, str]]:
    """Pull (url, headline) pairs from a search results page.

    Deliberately structure-agnostic: every publisher's markup differs and
    changes without notice, so anchors are filtered by shape -- a same-domain
    link with headline-length text -- rather than by CSS selectors that would
    silently stop matching.
    """
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return []

    results: list[tuple[str, str]] = []
    seen_urls: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        text = anchor.get_text(" ", strip=True)

        if len(text) < _MIN_HEADLINE_CHARS:
            continue

        url = urljoin(f"https://www.{site.domain}", href)
        if site.domain not in url or _NON_ARTICLE.search(url):
            continue
        if url in seen_urls:
            continue

        seen_urls.add(url)
        results.append((url, text))

        if len(results) >= 20:
            break

    return results


async def _search_site(
    client: httpx.AsyncClient, site: SearchableSite, query: str, queries: list[str]
) -> list[RetrievedItem]:
    """Query one publisher's search. Returns [] on any failure."""
    url = site.search_url.format(q=quote(query))

    try:
        response = await client.get(url)
        if response.status_code != 200:
            logger.info("site_search.non_200", site=site.name, status=response.status_code)
            return []
        html = response.text
    except Exception as exc:
        logger.info("site_search.failed", site=site.name, error_type=type(exc).__name__)
        return []

    pairs = await anyio.to_thread.run_sync(_extract_results, html, site)

    items: list[RetrievedItem] = []
    for result_url, headline in pairs:
        score = score_against_queries(headline, queries, language=site.language)
        if score <= 0:
            continue
        items.append(
            RetrievedItem(
                url=result_url,
                title=headline,
                # Body is fetched later, only for candidates worth reading.
                text="",
                source_domain=site.domain,
                source_name=site.name,
                source_type=site.source_type,
                language=site.language,
                provider=RetrievalProviderName.DIRECT_URL,
                score=score,
            )
        )

    logger.info("site_search.done", site=site.name, found=len(pairs), matched=len(items))
    return items


class SiteSearchProvider:
    """Searches publishers' own archives, beyond what RSS exposes."""

    name = RetrievalProviderName.DIRECT_URL

    def is_available(self) -> bool:
        return get_settings().site_search_enabled

    async def search(
        self, queries: list[str], *, limit: int = 20, language: str | None = None
    ) -> RetrievalOutcome:
        started = time.monotonic()
        settings = get_settings()

        if not self.is_available():
            return RetrievalOutcome(provider=self.name, error="site_search_disabled")
        if not queries:
            return RetrievalOutcome(provider=self.name, error="no_queries")

        # The full claim makes the best search string; the derived keyword
        # queries are used for scoring the results.
        query = _build_query(queries[0], language=language or "bn")

        sites = list(SEARCHABLE_SITES)
        if language:
            sites.sort(key=lambda s: s.language != language)
        sites = sites[: settings.site_search_max_sites]

        try:
            async with httpx.AsyncClient(
                headers={
                    "User-Agent": settings.user_agent,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "bn,en;q=0.8",
                },
                follow_redirects=True,
                timeout=settings.site_search_timeout_seconds,
            ) as client:
                import asyncio

                results = await asyncio.gather(
                    *(_search_site(client, site, query, queries) for site in sites),
                    return_exceptions=True,
                )
        except Exception as exc:
            return RetrievalOutcome(
                provider=self.name,
                duration_ms=int((time.monotonic() - started) * 1000),
                error=f"search_failed:{type(exc).__name__}",
            )

        items: list[RetrievedItem] = []
        for result in results:
            if isinstance(result, list):
                items.extend(result)

        items.sort(key=lambda i: i.score, reverse=True)

        return RetrievalOutcome(
            provider=self.name,
            items=items[:limit],
            duration_ms=int((time.monotonic() - started) * 1000),
            error=None if items else "no_matches",
        )
