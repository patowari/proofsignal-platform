"""Retrieval operations used by the verification pipeline.

Bridges the async retrieval providers to the synchronous worker, and turns
retrieved documents into persisted Source, RetrievedDocument, and Evidence rows.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.llm import LLMProvider
from app.core.config import get_settings
from app.core.enums import EvidenceRelationship, SourceType
from app.core.logging import get_logger
from app.core.versions import CLASSIFIER_VERSION
from app.models import Evidence, EvidenceCluster, RetrievedDocument, Source
from app.retrieval.article import fetch_article
from app.retrieval.base import RetrievedItem
from app.retrieval.evidence import ExtractedEvidence, extract_evidence_for_claim
from app.retrieval.feeds import RSSFeedProvider, is_primary_source_domain

logger = get_logger(__name__)


@dataclass(slots=True)
class ClaimEvidenceResult:
    """Everything retrieval produced for one claim."""

    claim_id: int
    documents_found: int = 0
    evidence_created: int = 0
    queries_run: list[str] | None = None
    providers_used: list[str] | None = None
    errors: list[str] | None = None


def run_async(coro):  # type: ignore[no-untyped-def]
    """Run an async coroutine from the synchronous worker.

    The worker is synchronous by design -- the pipeline is a sequence of
    dependent steps with no concurrency to exploit -- but retrieval is I/O
    bound and benefits from async internally.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        # Already inside a loop (tests): run on a separate thread's loop.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()

    return asyncio.run(coro)


def _domain_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def get_or_create_source(
    session: Session,
    domain: str,
    *,
    name: str | None = None,
    source_type: SourceType = SourceType.UNKNOWN,
    language: str | None = None,
) -> Source | None:
    """Find or create a Source row.

    Sources are shared across verifications, so the same publisher is one row
    and evidence clustering can reason about publisher identity.
    """
    if not domain:
        return None

    source = session.execute(select(Source).where(Source.domain == domain)).scalar_one_or_none()

    if source is None:
        source = Source(
            domain=domain,
            name=name or domain,
            source_type=source_type,
            language=language,
        )
        session.add(source)
        session.flush()
    elif source.source_type is SourceType.UNKNOWN and source_type is not SourceType.UNKNOWN:
        # Upgrade a placeholder created by an earlier direct-URL submission.
        source.source_type = source_type
        if name and not source.name:
            source.name = name

    return source


def retrieve_candidates(
    queries: list[str], *, language: str, limit: int
) -> tuple[list[RetrievedItem], list[str]]:
    """Query all available providers. Returns (items, errors)."""
    providers = [RSSFeedProvider()]
    items: list[RetrievedItem] = []
    errors: list[str] = []

    for provider in providers:
        if not provider.is_available():
            errors.append(f"{provider.name.value}:unavailable")
            continue

        outcome = run_async(provider.search(queries, limit=limit, language=language))
        if outcome.error:
            errors.append(f"{provider.name.value}:{outcome.error}")
        items.extend(outcome.items)

    return items, errors


def deduplicate_candidates(items: list[RetrievedItem]) -> list[RetrievedItem]:
    """Collapse duplicate candidates before spending fetches on them.

    Same canonical URL is the same document. Keeps the highest-scoring copy.
    """
    best: dict[str, RetrievedItem] = {}
    for item in items:
        key = item.dedup_url.rstrip("/").lower()
        existing = best.get(key)
        if existing is None or item.score > existing.score:
            best[key] = item
    return sorted(best.values(), key=lambda i: i.score, reverse=True)


def cluster_by_origin(
    session: Session, verification_id: int, documents: list[RetrievedDocument]
) -> dict[int, int]:
    """Group documents that are copies of one report.

    Returns document_id -> cluster_id.

    This is what stops widespread republication from reading as independent
    corroboration. V1 heuristics: identical content hash, or identical
    normalized title. Embedding-based near-duplicate detection comes with the
    vector retrieval phase.
    """
    groups: dict[str, list[RetrievedDocument]] = {}

    for document in documents:
        if document.content_hash:
            key = f"hash:{document.content_hash}"
        elif document.title:
            normalized = " ".join(document.title.lower().split())[:120]
            key = f"title:{hashlib.sha256(normalized.encode()).hexdigest()[:16]}"
        else:
            key = f"url:{document.canonical_url or document.url}"
        groups.setdefault(key, []).append(document)

    assignment: dict[int, int] = {}
    for key, members in groups.items():
        if len(members) == 1:
            continue  # a lone document is its own origin; no cluster row needed

        # Earliest publication is the most likely original.
        representative = min(
            members,
            key=lambda d: (d.published_at is None, d.published_at or d.created_at),
        )
        cluster = EvidenceCluster(
            verification_id=verification_id,
            representative_document_id=representative.id,
            member_count=len(members),
            clustering_method=key.split(":", 1)[0],
            similarity_score=1.0,
        )
        session.add(cluster)
        session.flush()
        for member in members:
            assignment[member.id] = cluster.id

    return assignment


def persist_document(
    session: Session, item: RetrievedItem, *, body_text: str | None = None
) -> RetrievedDocument:
    """Store a retrieved document, reusing an existing row when we have it."""
    domain = item.source_domain or _domain_of(item.url)
    source = get_or_create_source(
        session,
        domain,
        name=item.source_name,
        source_type=item.source_type,
        language=item.language,
    )

    canonical = (item.canonical_url or item.url).rstrip("/")
    existing = session.execute(
        select(RetrievedDocument).where(RetrievedDocument.canonical_url == canonical)
    ).scalar_one_or_none()

    excerpt = (body_text or item.text or "")[:2000]
    content_hash = (
        hashlib.sha256((body_text or item.text or "").encode()).hexdigest()
        if (body_text or item.text)
        else None
    )

    if existing is not None:
        if body_text and len(body_text) > len(existing.excerpt or ""):
            existing.excerpt = excerpt
            existing.content_hash = content_hash
        return existing

    document = RetrievedDocument(
        source_id=source.id if source else None,
        url=item.url,
        canonical_url=canonical,
        title=item.title,
        published_at=item.published_at,
        excerpt=excerpt,
        language=item.language,
        content_hash=content_hash,
        retrieval_provider=item.provider,
        fetch_status="ok",
    )
    session.add(document)
    session.flush()
    return document


def build_evidence_for_claim(
    session: Session,
    *,
    claim_id: int,
    claim_text: str,
    queries: list[str],
    language: str,
    candidates: list[RetrievedItem],
) -> ClaimEvidenceResult:
    """Fetch article bodies, extract passages, and persist evidence rows."""
    settings = get_settings()
    result = ClaimEvidenceResult(claim_id=claim_id, queries_run=queries)

    if not candidates:
        return result

    # Fetching bodies is the expensive part, so it is capped. Feed summaries
    # are used for anything beyond the cap.
    to_fetch = candidates[: settings.max_article_fetches]
    documents: list[tuple[RetrievedDocument, str, RetrievedItem]] = []

    for item in to_fetch:
        article = run_async(fetch_article(item.url))

        if article is not None:
            body = article.text
            if article.canonical_url:
                item.canonical_url = article.canonical_url
            if article.published_at and not item.published_at:
                item.published_at = article.published_at
            if article.title:
                item.title = article.title or item.title
        else:
            # Fall back to the feed summary rather than dropping the source.
            body = item.text

        if not body:
            continue

        document = persist_document(session, item, body_text=body)
        if article is not None and article.injection_detected:
            document.injection_detected = True
            document.injection_signals = list(article.injection_signals)
        documents.append((document, body, item))

    result.documents_found = len(documents)
    if not documents:
        return result

    verification_id = _verification_of(session, claim_id)
    clusters = cluster_by_origin(
        session, verification_id, [document for document, _, _ in documents]
    )

    for document, body, _item in documents:
        passages = extract_evidence_for_claim(claim_text, body, queries, language=language)
        for passage in passages:
            # Neutral passages are recorded so the report can show what was
            # checked, but they add no weight to the verdict.
            evidence = Evidence(
                claim_id=claim_id,
                document_id=document.id,
                source_id=document.source_id,
                cluster_id=clusters.get(document.id),
                evidence_text=passage.passage,
                relationship_type=passage.relationship,
                relevance_score=passage.relevance,
                strength_score=passage.relevance * passage.directness,
                directness=passage.directness,
                source_factor=None,
                classifier_name=passage.classifier,
                classifier_version=CLASSIFIER_VERSION,
                classifier_confidence=passage.confidence,
                weight_breakdown={
                    "rationale": passage.rationale,
                    "is_primary_source": is_primary_source_domain(
                        document.source.domain if document.source else ""
                    ),
                },
            )
            session.add(evidence)
            result.evidence_created += 1

    session.flush()
    return result


def _verification_of(session: Session, claim_id: int) -> int:
    """Look up a claim's verification id, needed for cluster ownership."""
    from app.models import Claim

    return session.execute(select(Claim.verification_id).where(Claim.id == claim_id)).scalar_one()


def signals_from_evidence(
    session: Session, claim_id: int
) -> list[tuple[EvidenceRelationship, float, SourceType, bool, int | None]]:
    """Load persisted evidence in the shape the scorer needs."""
    rows = session.execute(select(Evidence).where(Evidence.claim_id == claim_id)).scalars().all()

    signals = []
    for row in rows:
        source_type = SourceType.UNKNOWN
        is_primary = False
        if row.source_id is not None:
            source = session.get(Source, row.source_id)
            if source is not None:
                source_type = source.source_type
                is_primary = is_primary_source_domain(source.domain)

        signals.append(
            (
                row.relationship_type,
                row.relevance_score,
                source_type,
                is_primary,
                row.cluster_id,
            )
        )
    return signals


def _reclassify_with_llm(
    llm: LLMProvider,
    claim_text: str,
    passages: list[ExtractedEvidence],
    language: str,
) -> list[ExtractedEvidence]:
    """Re-label lexically-selected passages using the LLM.

    Retrieval still selects *which* passages are candidates -- that is cheap and
    deterministic. The model only decides the relationship, which is the part
    lexical rules get wrong across paraphrase and across languages.

    Any failure keeps the lexical label, so a slow or absent model degrades
    quality rather than losing the evidence.
    """
    from app.ai.classifier import CLASSIFIER_NAME, classify_with_llm

    updated = []
    for passage in passages:
        try:
            result = run_async(
                classify_with_llm(llm, claim_text, passage.passage, language=language)
            )
        except Exception as exc:
            logger.warning("classifier.failed", error_type=type(exc).__name__)
            result = None

        if result is None:
            updated.append(passage)
            continue

        passage.relationship = result.relationship
        passage.directness = result.directness
        passage.rationale = result.reason
        passage.confidence = result.confidence
        passage.classifier = CLASSIFIER_NAME
        updated.append(passage)

    return updated
