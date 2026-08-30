"""Stage implementations.

Retrieval searches the news sources configured in `infrastructure/feeds.yaml`
and any URL the user submits. It does NOT search the whole web, and the report
says so: coverage is what we actually queried, nothing more.

When retrieval finds nothing relevant, the verdict is UNVERIFIED and the report
states that plainly. We never invent evidence to make a result look more
confident, and fixture data exists only inside tests -- never in a real run.
See docs/PRODUCT.md.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.core.enums import (
    ClaimOrigin,
    PipelineStage,
    RetrievalProviderName,
)
from app.core.errors import StageFailedError
from app.core.logging import get_logger
from app.core.versions import CLAIM_EXTRACTION_VERSION
from app.models import Claim, RetrievalQuery
from app.retrieval.pipeline_ops import (
    build_evidence_for_claim,
    deduplicate_candidates,
    retrieve_candidates,
    signals_from_evidence,
)
from app.retrieval.scoring import build_queries
from app.verification.claim_extraction import extract_claims
from app.verification.language import detect_language
from app.verification.pipeline import PipelineContext
from app.verification.scoring import (
    ClaimSignals,
    EvidenceSignal,
    score_claim,
    score_overall,
)

logger = get_logger(__name__)


def stage_normalizing(ctx: PipelineContext) -> dict[str, Any]:
    """Collect the text to analyze, tagged by where it came from.

    Origin is preserved because a user's caption and a video's transcript are
    different assertions by different authors and must be verified separately.
    """
    submission = ctx.submission

    if submission.text:
        ctx.text_by_origin[ClaimOrigin.USER_TEXT.value] = submission.text
    if submission.caption:
        ctx.text_by_origin[ClaimOrigin.USER_CAPTION.value] = submission.caption

    if not ctx.text_by_origin and not submission.submitted_url and not submission.media_assets:
        raise StageFailedError(
            PipelineStage.NORMALIZING.value,
            "This submission contains nothing to verify.",
        )

    return {
        "origins": list(ctx.text_by_origin),
        "total_chars": sum(len(t) for t in ctx.text_by_origin.values()),
        "has_media": bool(submission.media_assets),
        "has_url": bool(submission.submitted_url),
    }


def stage_extracting_content(ctx: PipelineContext) -> dict[str, Any]:
    """Fetch and extract the text of a submitted URL.

    The article body becomes the content we extract claims from, so a URL
    submission is verified on what the page actually says rather than on its
    address.
    """
    url = ctx.submission.submitted_url
    if not url:
        return {"skipped": True, "reason": "no_url"}

    from app.retrieval.article import fetch_article
    from app.retrieval.pipeline_ops import run_async

    article = run_async(fetch_article(url))

    if article is None:
        # Inaccessible content is reported honestly. We do not bypass paywalls,
        # logins, or platform restrictions, and we never pretend we read a page
        # we could not reach.
        ctx.degrade("url_content_unavailable")
        return {
            "degraded": True,
            "reason": "url_content_unavailable",
            "detail": (
                "We could not read this page. It may be paywalled, private, "
                "removed, or blocking automated readers."
            ),
        }

    ctx.text_by_origin[ClaimOrigin.ARTICLE_TEXT.value] = article.text
    if article.canonical_url:
        ctx.submission.canonical_url = article.canonical_url
    if article.title and not ctx.submission.title:
        ctx.submission.title = article.title[:500]
    ctx.session.flush()

    return {
        "chars_extracted": len(article.text),
        "title": (article.title or "")[:120],
        "published_at": article.published_at.isoformat() if article.published_at else None,
        # A page trying to instruct an automated reader is reported as a
        # property of that source; it can never change a verdict.
        "injection_detected": article.injection_detected,
    }


def stage_detecting_language(ctx: PipelineContext) -> dict[str, Any]:
    """Detect the language of the submitted text."""
    combined = " ".join(ctx.text_by_origin.values())
    if not combined.strip():
        ctx.language = "en"
        return {"language": "en", "reason": "no_text"}

    ctx.language = detect_language(combined)
    ctx.submission.detected_language = ctx.language
    return {"language": ctx.language, "sample_chars": len(combined)}


def stage_extracting_claims(ctx: PipelineContext) -> dict[str, Any]:
    """Decompose the content into atomic, independently checkable claims."""
    if not ctx.text_by_origin:
        raise StageFailedError(
            PipelineStage.EXTRACTING_CLAIMS.value,
            "There is no text to extract claims from.",
        )

    total = 0
    for origin_value, text in ctx.text_by_origin.items():
        origin = ClaimOrigin(origin_value)
        extracted = extract_claims(text, language=ctx.language, origin=origin)

        for index, item in enumerate(extracted):
            claim = Claim(
                verification_id=ctx.verification.id,
                claim_text=item.claim_text,
                normalized_claim=item.normalized_claim,
                language=item.language,
                claim_type=item.claim_type,
                origin=origin,
                importance=item.importance,
                sequence=total + index,
                dates=item.dates or None,
                numbers=item.numbers or None,
                money=item.money or None,
                percentages=item.percentages or None,
                locations=item.locations or None,
            )
            ctx.session.add(claim)
            ctx.claims.append(claim)
        total += len(extracted)

    ctx.session.flush()

    if not ctx.claims:
        # A media submission with no caption and no readable text has nothing to
        # check against evidence -- but the file analysis (metadata, provenance,
        # capture date) is still worth reporting. Failing here would throw that
        # away and tell the user nothing.
        if ctx.submission.media_assets:
            ctx.degrade("no_claims_from_media")
            return {
                "claim_count": 0,
                "degraded": True,
                "reason": "no_checkable_claim",
                "detail": (
                    "No caption was given and no text could be read from the file, so "
                    "there is no factual claim to check. The file analysis below still "
                    "applies."
                ),
            }
        raise StageFailedError(
            PipelineStage.EXTRACTING_CLAIMS.value,
            "No verifiable factual claims were found in this submission.",
        )

    return {
        "claim_count": len(ctx.claims),
        "extraction_version": CLAIM_EXTRACTION_VERSION,
        "method": "rule_based",
    }


def stage_generating_queries(ctx: PipelineContext) -> dict[str, Any]:
    """Build retrieval queries for each claim.

    Several query shapes per claim, because one form rarely serves every
    source: the full claim matches close paraphrases, while a keyword-only form
    matches reports that word the same facts differently.
    """
    if not ctx.claims:
        return {"skipped": True, "reason": "no_claims"}

    total = 0
    for claim in ctx.claims:
        queries = build_queries(claim.claim_text, language=claim.language)
        ctx.queries.append((claim, queries))
        total += len(queries)

    return {"claims": len(ctx.claims), "queries_generated": total}


def stage_retrieving_evidence(ctx: PipelineContext) -> dict[str, Any]:
    """Search configured sources for documents relevant to each claim.

    Coverage is limited to what is configured plus any submitted URL. Finding
    nothing is a legitimate outcome, recorded honestly rather than papered over.
    """
    from app.core.config import get_settings

    if not ctx.queries:
        return {"skipped": True, "reason": "no_queries"}

    settings = get_settings()
    total_candidates = 0
    provider_errors: list[str] = []

    for claim, queries in ctx.queries:
        if not queries:
            continue

        candidates, errors = retrieve_candidates(
            queries,
            language=claim.language,
            limit=settings.retrieval_candidate_limit,
        )
        provider_errors.extend(errors)

        candidates = [
            c for c in deduplicate_candidates(candidates) if c.score >= settings.retrieval_min_score
        ]
        ctx.retrieved_documents.append((claim, queries, candidates))
        total_candidates += len(candidates)

        # Log every query we ran, so "sources checked" is auditable rather than
        # asserted.
        for query in queries:
            ctx.session.add(
                RetrievalQuery(
                    claim_id=claim.id,
                    query_text=query[:2000],
                    language=claim.language,
                    provider=RetrievalProviderName.RSS_CORPUS,
                    result_count=len(candidates),
                    error="; ".join(provider_errors)[:255] or None,
                )
            )

    ctx.session.flush()

    if provider_errors:
        ctx.degrade("some_sources_unreachable")

    if total_candidates == 0:
        # Not a failure: no relevant coverage is a real and common finding.
        return {
            "documents_found": 0,
            "detail": "No relevant articles were found in the sources we checked.",
            "provider_errors": provider_errors[:5],
        }

    return {
        "documents_found": total_candidates,
        "claims_searched": len(ctx.queries),
        "provider_errors": provider_errors[:5],
    }


def stage_fetching_documents(ctx: PipelineContext) -> dict[str, Any]:
    """Report the candidate set.

    Bodies are fetched in EXTRACTING_EVIDENCE, where each fetch can be tied to
    the claim it serves and the per-verification fetch budget applies.
    """
    if not ctx.retrieved_documents:
        return {"skipped": True, "reason": "no_candidates"}
    total = sum(len(candidates) for _, _, candidates in ctx.retrieved_documents)
    return {"candidates": total}


def stage_extracting_evidence(ctx: PipelineContext) -> dict[str, Any]:
    """Fetch article bodies and extract claim-relevant passages.

    A retrieved document is not evidence. Evidence is the specific passage that
    speaks to a specific claim, which is what this stage isolates.
    """
    if not ctx.retrieved_documents:
        return {"skipped": True, "reason": "no_documents"}

    total_documents = 0
    total_evidence = 0

    for claim, queries, candidates in ctx.retrieved_documents:
        if not candidates:
            continue
        result = build_evidence_for_claim(
            ctx.session,
            claim_id=claim.id,
            claim_text=claim.claim_text,
            queries=queries,
            language=claim.language,
            candidates=candidates,
        )
        total_documents += result.documents_found
        total_evidence += result.evidence_created
        ctx.evidence.append(result)

    return {"documents_read": total_documents, "evidence_extracted": total_evidence}


def stage_classifying_evidence(ctx: PipelineContext) -> dict[str, Any]:
    """Confirm evidence labelling.

    Classification happens during extraction, where the passage and its claim
    are both in hand. This stage reports the resulting distribution so the
    progress UI and the stored record show what was actually decided.
    """
    if not ctx.evidence:
        return {"skipped": True, "reason": "no_evidence"}

    from app.models import Evidence as EvidenceModel

    counts: dict[str, int] = {}
    for result in ctx.evidence:
        rows = (
            ctx.session.execute(
                select(EvidenceModel).where(EvidenceModel.claim_id == result.claim_id)
            )
            .scalars()
            .all()
        )
        for row in rows:
            counts[row.relationship_type.value] = counts.get(row.relationship_type.value, 0) + 1

    return {"classified": sum(counts.values()), "distribution": counts}


def stage_analyzing_media(ctx: PipelineContext) -> dict[str, Any]:
    """Analyze uploaded media: metadata, provenance, and embedded text.

    Two rules govern this stage.

    We do NOT claim to detect AI-generated images. No reliable general detector
    exists, and a confident wrong answer here is a serious harm in both
    directions. We report the provenance evidence we actually find, each with
    its limits stated.

    A missing capability is recorded as unavailable with a reason, never as a
    finding about the file. "No OCR engine installed" must never reach a reader
    as "no text found in this image".
    """
    from app.core.enums import AnalysisAvailability, MediaKind
    from app.media.image_analysis import analyze_image, extract_text
    from app.models import MediaAnalysis
    from app.services.storage import get_storage

    assets = ctx.submission.media_assets
    if not assets:
        return {"skipped": True, "reason": "no_media"}

    settings = get_settings_for_media()
    storage = get_storage()

    analyzed = 0
    ocr_chars = 0
    signals_found = 0
    degraded_reasons: list[str] = []

    for asset in assets:
        if asset.kind is MediaKind.VIDEO:
            # Video analysis is a later phase. Recorded honestly rather than
            # silently skipped.
            ctx.degrade("video_analysis_not_implemented")
            degraded_reasons.append("video_analysis_not_implemented")
            continue

        try:
            data = storage.get(asset.storage_key)
        except Exception as exc:
            logger.warning("media.read_failed", error_type=type(exc).__name__)
            degraded_reasons.append("media_unreadable")
            continue

        forensics = analyze_image(data)

        # OCR: extracted text becomes claims of its own, tagged OCR_TEXT so the
        # report keeps them separate from the user's caption.
        ocr_text, ocr_reason = extract_text(data, languages=settings.ocr_languages)
        if ocr_text is None:
            ocr_status = AnalysisAvailability.UNAVAILABLE
            ctx.degrade("ocr_unavailable")
        else:
            ocr_status = AnalysisAvailability.COMPLETED
            ocr_chars += len(ocr_text)
            if ocr_text.strip():
                existing = ctx.text_by_origin.get(ClaimOrigin.OCR_TEXT.value, "")
                ctx.text_by_origin[ClaimOrigin.OCR_TEXT.value] = f"{existing}\n{ocr_text}".strip()

        analysis = MediaAnalysis(
            verification_id=ctx.verification.id,
            media_asset_id=asset.id,
            kind=asset.kind,
            metadata_findings={
                "width": forensics.width,
                "height": forensics.height,
                "format": forensics.format,
                "camera": forensics.camera,
                "software": forensics.software,
                "generator": forensics.generator,
                "has_c2pa": forensics.has_c2pa,
                "has_exif": forensics.has_exif,
                # Deliberately not a verdict: "declared_generator",
                # "provenance_present", or "undetermined".
                "ai_generation_assessment": forensics.ai_generation_assessment,
            },
            manipulation_signals=[
                {
                    "type": signal.key,
                    "description": signal.finding,
                    "caveat": signal.caveat,
                    "strength": signal.strength,
                }
                for signal in forensics.signals
            ],
            metadata_captured_at=forensics.captured_at,
            ocr_status=ocr_status,
            ocr_text=(ocr_text or None),
            ocr_engine="tesseract" if ocr_text is not None else None,
            ocr_unavailable_reason=(ocr_reason or None) if ocr_text is None else None,
            analysis_availability={
                "metadata": AnalysisAvailability.COMPLETED.value,
                "ocr": ocr_status.value,
                # Stated explicitly so the report can explain the absence rather
                # than leaving a reader to assume we checked.
                "ai_detection": AnalysisAvailability.UNAVAILABLE.value,
                "ai_detection_reason": (
                    "No reliable general detector for AI-generated images exists. "
                    "We report provenance metadata instead of guessing."
                ),
                "reverse_image_search": AnalysisAvailability.UNAVAILABLE.value,
            },
        )
        ctx.session.add(analysis)
        ctx.media_analyses.append(analysis)
        analyzed += 1
        signals_found += len(forensics.signals)

    ctx.session.flush()

    return {
        "assets_analyzed": analyzed,
        "signals_found": signals_found,
        "ocr_chars": ocr_chars,
        "degraded": bool(degraded_reasons),
        "degradation": degraded_reasons[:3],
    }


def get_settings_for_media():  # type: ignore[no-untyped-def]
    """Settings accessor kept local so the stage module has no import cycle."""
    from app.core.config import get_settings

    return get_settings()


def stage_scoring(ctx: PipelineContext) -> dict[str, Any]:
    """Score every claim and compute the overall verdict.

    Fully implemented and deterministic. With no evidence it correctly yields
    UNVERIFIED at LOW confidence.
    """
    if not ctx.claims:
        if ctx.submission.media_assets:
            # Nothing to score, but the media findings still form a report.
            ctx.verification.overall_verdict = None
            ctx.verification.confidence_band = None
            return {"claims_scored": 0, "reason": "media_only_submission"}
        raise StageFailedError(PipelineStage.SCORING.value, "There are no claims to score.")

    claim_scores = []
    importances: dict[str, float] = {}

    for claim in ctx.claims:
        claim_id = str(claim.id)
        importances[claim_id] = claim.importance

        # Load the evidence retrieval actually found. An empty list is a
        # legitimate outcome and scoring handles it by returning UNVERIFIED.
        evidence_signals = tuple(
            EvidenceSignal(
                relationship=relationship,
                relevance=relevance,
                source_type=source_type,
                is_primary_source=is_primary,
                # Items sharing a cluster are copies of one report, so only the
                # strongest counts fully. This is what stops republication from
                # reading as independent corroboration.
                cluster_id=str(cluster_id) if cluster_id is not None else None,
            )
            for relationship, relevance, source_type, is_primary, cluster_id in (
                signals_from_evidence(ctx.session, claim.id)
            )
        )

        signals = ClaimSignals(
            claim_id=claim_id,
            claim_type=claim.claim_type,
            importance=claim.importance,
            evidence=evidence_signals,
            penalties=(),
        )
        score = score_claim(signals)
        claim_scores.append(score)

        claim.verdict = score.verdict
        claim.confidence_band = score.confidence_band
        claim.score_breakdown = score.to_breakdown()

    overall = score_overall(
        tuple(claim_scores),
        importances,
        degraded=ctx.degraded,
        degradation_reasons=tuple(ctx.degradation_reasons),
    )

    ctx.verification.overall_verdict = overall.verdict
    ctx.verification.confidence_band = overall.confidence_band
    ctx.verification.confidence_score = overall.confidence_score
    ctx.verification.score_breakdown = overall.to_breakdown()
    ctx.session.flush()

    return {
        "claims_scored": len(claim_scores),
        "overall_verdict": overall.verdict.value,
        "confidence_band": overall.confidence_band.value,
    }


def stage_generating_report(ctx: PipelineContext) -> dict[str, Any]:
    """Write the plain-language summary.

    Built from what actually happened, so it cannot overstate what we did.
    """
    from app.models import Evidence as EvidenceModel
    from app.models import Source

    verification = ctx.verification
    claim_count = len(ctx.claims)

    claim_ids = [c.id for c in ctx.claims]
    rows = (
        ctx.session.execute(select(EvidenceModel).where(EvidenceModel.claim_id.in_(claim_ids)))
        .scalars()
        .all()
        if claim_ids
        else []
    )

    supporting = sum(1 for r in rows if r.relationship_type.value == "SUPPORTS")
    contradicting = sum(1 for r in rows if r.relationship_type.value == "CONTRADICTS")
    origins = len({r.cluster_id for r in rows if r.cluster_id is not None}) + sum(
        1 for r in rows if r.cluster_id is None
    )

    source_ids = {r.source_id for r in rows if r.source_id is not None}
    publishers = []
    for source_id in list(source_ids)[:6]:
        source = ctx.session.get(Source, source_id)
        if source and source.name:
            publishers.append(source.name)

    claim_word = "claim" if claim_count == 1 else "claims"

    if not rows:
        # Say what we searched and that finding nothing is not a finding of
        # falsehood. This is the most important sentence in the product.
        summary = (
            f"We identified {claim_count} factual {claim_word} in this submission and "
            f"searched our indexed news sources, but found nothing relevant enough to "
            f"confirm or contradict {'it' if claim_count == 1 else 'them'}. "
            "That means the claim is unverified — it does not mean it is false. "
            "Our coverage is limited to the sources we index, so absence here is not "
            "absence everywhere."
        )
    else:
        parts = [
            f"We identified {claim_count} factual {claim_word} and examined "
            f"{len(rows)} passages from {origins} independent "
            f"{'source' if origins == 1 else 'sources'}."
        ]
        if supporting and contradicting:
            parts.append(
                f"{supporting} passage{'s' if supporting != 1 else ''} supported the "
                f"claims and {contradicting} contradicted them."
            )
        elif supporting:
            parts.append(
                f"{supporting} passage{'s' if supporting != 1 else ''} supported the claims."
            )
        elif contradicting:
            parts.append(
                f"{contradicting} passage{'s' if contradicting != 1 else ''} contradicted "
                "the claims."
            )
        else:
            parts.append(
                "The passages we found were related but did not settle the claims either way."
            )
        if publishers:
            parts.append("Sources checked: " + ", ".join(sorted(publishers)) + ".")
        summary = " ".join(parts)

    verification.summary = summary
    ctx.session.flush()

    return {"summary_length": len(summary), "claim_count": claim_count}


#: Stage wiring used by the worker.
DEFAULT_STAGES = {
    PipelineStage.NORMALIZING: stage_normalizing,
    PipelineStage.EXTRACTING_CONTENT: stage_extracting_content,
    PipelineStage.DETECTING_LANGUAGE: stage_detecting_language,
    PipelineStage.EXTRACTING_CLAIMS: stage_extracting_claims,
    PipelineStage.GENERATING_QUERIES: stage_generating_queries,
    PipelineStage.RETRIEVING_EVIDENCE: stage_retrieving_evidence,
    PipelineStage.FETCHING_DOCUMENTS: stage_fetching_documents,
    PipelineStage.EXTRACTING_EVIDENCE: stage_extracting_evidence,
    PipelineStage.CLASSIFYING_EVIDENCE: stage_classifying_evidence,
    PipelineStage.ANALYZING_MEDIA: stage_analyzing_media,
    PipelineStage.SCORING: stage_scoring,
    PipelineStage.GENERATING_REPORT: stage_generating_report,
}
