"""Stage implementations.

Current state: normalization, language detection, claim extraction, and scoring
are real. Retrieval and evidence analysis are NOT yet implemented -- those land
in later roadmap phases.

The honest consequence, which this module enforces: with no retrieval there is
no evidence, and with no evidence every claim scores UNVERIFIED. That is the
correct answer, and the report says plainly that evidence retrieval was
unavailable. We never invent evidence to make the output look better, and we
never let a fixture leak into a production run -- fixtures exist only inside
tests. See docs/PRODUCT.md.
"""

from __future__ import annotations

from typing import Any

from app.core.enums import (
    ClaimOrigin,
    PipelineStage,
)
from app.core.errors import StageFailedError
from app.core.logging import get_logger
from app.core.versions import CLAIM_EXTRACTION_VERSION
from app.models import Claim
from app.verification.claim_extraction import extract_claims
from app.verification.language import detect_language
from app.verification.pipeline import PipelineContext
from app.verification.scoring import ClaimSignals, score_claim, score_overall

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
    """Fetch and extract content from a submitted URL.

    Not yet implemented. Rather than silently producing an empty result, this
    records that URL content could not be retrieved, so the report can say so.
    """
    if not ctx.submission.submitted_url:
        return {"skipped": True, "reason": "no_url"}

    ctx.degrade("url_extraction_not_implemented")
    return {
        "degraded": True,
        "reason": "article_extraction_not_implemented",
        "detail": "URL content extraction is not yet available; only the URL itself was recorded.",
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
    """Build retrieval queries, including cross-language variants.

    Not yet implemented -- lands with the retrieval phase.
    """
    ctx.degrade("query_generation_not_implemented")
    return {
        "degraded": True,
        "reason": "query_generation_not_implemented",
    }


def stage_retrieving_evidence(ctx: PipelineContext) -> dict[str, Any]:
    """Query retrieval providers.

    Not yet implemented. No evidence is produced, and none is invented: the
    downstream effect is that claims score UNVERIFIED, which is the honest
    outcome when nothing has been checked.
    """
    ctx.degrade("evidence_retrieval_not_implemented")
    return {
        "degraded": True,
        "reason": "evidence_retrieval_not_implemented",
        "detail": "No retrieval providers are active yet, so no evidence was gathered.",
        "documents_found": 0,
    }


def stage_fetching_documents(ctx: PipelineContext) -> dict[str, Any]:
    if not ctx.retrieved_documents:
        return {"skipped": True, "reason": "no_candidates"}
    return {"documents": len(ctx.retrieved_documents)}


def stage_extracting_evidence(ctx: PipelineContext) -> dict[str, Any]:
    if not ctx.retrieved_documents:
        return {"skipped": True, "reason": "no_documents"}
    return {"evidence_items": len(ctx.evidence)}


def stage_classifying_evidence(ctx: PipelineContext) -> dict[str, Any]:
    if not ctx.evidence:
        return {"skipped": True, "reason": "no_evidence"}
    return {"classified": len(ctx.evidence)}


def stage_analyzing_media(ctx: PipelineContext) -> dict[str, Any]:
    """Analyze uploaded media.

    Not yet implemented. Recorded as unavailable rather than as "nothing found",
    so our own gap is never presented as a finding about the user's file.
    """
    assets = ctx.submission.media_assets
    if not assets:
        return {"skipped": True, "reason": "no_media"}

    ctx.degrade("media_analysis_not_implemented")
    return {
        "degraded": True,
        "reason": "media_analysis_not_implemented",
        "asset_count": len(assets),
        "detail": "Media analysis is not yet available; the file was stored but not analyzed.",
    }


def stage_scoring(ctx: PipelineContext) -> dict[str, Any]:
    """Score every claim and compute the overall verdict.

    Fully implemented and deterministic. With no evidence it correctly yields
    UNVERIFIED at LOW confidence.
    """
    if not ctx.claims:
        raise StageFailedError(PipelineStage.SCORING.value, "There are no claims to score.")

    claim_scores = []
    importances: dict[str, float] = {}

    for claim in ctx.claims:
        claim_id = str(claim.id)
        importances[claim_id] = claim.importance

        # Evidence is empty until retrieval exists; scoring handles that
        # correctly by returning UNVERIFIED rather than guessing.
        signals = ClaimSignals(
            claim_id=claim_id,
            claim_type=claim.claim_type,
            importance=claim.importance,
            evidence=(),
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
    verification = ctx.verification
    claim_count = len(ctx.claims)
    evidence_count = len(ctx.evidence)

    if evidence_count == 0:
        summary = (
            f"We identified {claim_count} factual "
            f"{'claim' if claim_count == 1 else 'claims'} in this submission, but we were "
            f"not able to check {'it' if claim_count == 1 else 'them'} against any evidence. "
            "Evidence retrieval is not yet available in this build, so no sources were "
            "searched. This result means the claims are unverified — it does not mean they "
            "are false."
        )
    else:
        summary = (
            f"We identified {claim_count} factual "
            f"{'claim' if claim_count == 1 else 'claims'} and examined {evidence_count} "
            f"pieces of evidence."
        )

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
