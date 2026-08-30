"""Verification read endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import db_session, rate_limit, validate_verification_id
from app.core.enums import EvidenceRelationship, PipelineStage, Verdict, VerificationStatus
from app.core.errors import NotFoundError
from app.models import Claim, Evidence, Submission, Verification
from app.schemas.verification import (
    ClaimResponse,
    EvidenceResponse,
    MediaAnalysisResponse,
    RecentListResponse,
    RecentVerificationResponse,
    StageResponse,
    SubmissionResponse,
    VerificationReportResponse,
    VerificationStatusResponse,
)
from app.services.rate_limit import RateLimitOperation
from app.verification.pipeline import STAGE_SEQUENCE

router = APIRouter(tags=["verifications"])


async def _load_verification(session: AsyncSession, public_id: str) -> Verification:
    verification = (
        await session.execute(
            select(Verification)
            .where(Verification.public_id == public_id)
            .options(
                selectinload(Verification.stages),
                selectinload(Verification.submission).selectinload(Submission.media_assets),
                selectinload(Verification.media_analyses),
            )
        )
    ).scalar_one_or_none()

    if verification is None:
        raise NotFoundError("No verification was found with that id.")
    return verification


def _stage_responses(verification: Verification) -> list[StageResponse]:
    return [
        StageResponse(
            stage=s.stage,
            label=s.stage.label,
            status=s.status.value,
            sequence=s.sequence,
            started_at=s.started_at,
            finished_at=s.finished_at,
            duration_ms=s.duration_ms,
            error_type=s.error_type,
        )
        for s in sorted(verification.stages, key=lambda s: s.sequence)
    ]


@router.get("/verifications/{public_id}/status", response_model=VerificationStatusResponse)
async def get_status(
    public_id: str = Depends(validate_verification_id),
    session: AsyncSession = Depends(db_session),
    _: None = Depends(rate_limit(RateLimitOperation.STATUS_POLL)),
) -> VerificationStatusResponse:
    """Live progress.

    The cheap endpoint the UI polls. Built from real VerificationStage rows, so
    displayed progress cannot drift from what the worker is doing.
    """
    verification = await _load_verification(session, public_id)
    stages = _stage_responses(verification)

    has_media = bool(verification.submission.media_assets)
    expected = [s for s in STAGE_SEQUENCE if s is not PipelineStage.ANALYZING_MEDIA or has_media]
    completed = sum(1 for s in stages if s.status in ("COMPLETED", "SKIPPED", "DEGRADED"))

    return VerificationStatusResponse(
        public_id=verification.public_id,
        status=verification.status,
        current_stage=verification.current_stage,
        current_stage_label=verification.current_stage.label,
        stage_index=completed,
        stage_count=len(expected),
        stages=stages,
        degraded=verification.degraded,
        degradation_reasons=verification.degradation_reasons or [],
        error_code=verification.error_code,
        error_message=verification.error_message,
        created_at=verification.created_at,
        completed_at=verification.completed_at,
    )


async def _claim_responses(
    session: AsyncSession, verification: Verification, *, include_evidence: bool = True
) -> list[ClaimResponse]:
    claims = (
        (
            await session.execute(
                select(Claim)
                .where(Claim.verification_id == verification.id)
                .order_by(Claim.sequence)
                .options(selectinload(Claim.evidence).selectinload(Evidence.document))
            )
        )
        .scalars()
        .all()
    )

    responses: list[ClaimResponse] = []
    for claim in claims:
        evidence_items: list[EvidenceResponse] = []
        supporting = contradicting = 0
        clusters: set[int] = set()

        # An item with no cluster is its own origin; only clustered items share
        # one. Counting clusters alone reported zero origins whenever every
        # source was independent, which is the common case.
        standalone_origins: set[int] = set()

        for ev in claim.evidence:
            if ev.relationship_type is EvidenceRelationship.SUPPORTS:
                supporting += 1
            elif ev.relationship_type is EvidenceRelationship.CONTRADICTS:
                contradicting += 1
            if ev.cluster_id is not None:
                clusters.add(ev.cluster_id)
            elif ev.document_id is not None:
                standalone_origins.add(ev.document_id)

            if include_evidence:
                doc = ev.document
                evidence_items.append(
                    EvidenceResponse(
                        relationship=ev.relationship_type,
                        evidence_text=ev.evidence_text,
                        document_title=doc.title if doc else None,
                        document_url=doc.canonical_url or doc.url if doc else None,
                        published_at=doc.published_at if doc else None,
                        relevance_score=ev.relevance_score,
                        cluster_id=ev.cluster_id,
                    )
                )

        responses.append(
            ClaimResponse(
                claim_text=claim.claim_text,
                normalized_claim=claim.normalized_claim,
                language=claim.language,
                claim_type=claim.claim_type,
                origin=claim.origin,
                importance=claim.importance,
                sequence=claim.sequence,
                verdict=claim.verdict,
                confidence_band=claim.confidence_band,
                evidence=evidence_items,
                supporting_count=supporting,
                contradicting_count=contradicting,
                # Distinct origins, not raw counts: syndicated copies must never
                # be presented as independent corroboration.
                independent_origins=len(clusters) + len(standalone_origins),
            )
        )
    return responses


@router.get("/verifications/{public_id}", response_model=VerificationReportResponse)
async def get_verification(
    public_id: str = Depends(validate_verification_id),
    session: AsyncSession = Depends(db_session),
) -> VerificationReportResponse:
    """The full verification report."""
    verification = await _load_verification(session, public_id)
    claims = await _claim_responses(session, verification)
    submission = verification.submission

    total_evidence = sum(len(c.evidence) for c in claims)
    supporting = sum(c.supporting_count for c in claims)
    contradicting = sum(c.contradicting_count for c in claims)
    unresolved = sum(1 for c in claims if c.verdict is None or c.verdict is Verdict.UNVERIFIED)

    return VerificationReportResponse(
        public_id=verification.public_id,
        status=verification.status,
        submission=SubmissionResponse(
            public_id=submission.public_id,
            content_type=submission.content_type,
            title=submission.title,
            text=submission.text,
            caption=submission.caption,
            submitted_url=submission.submitted_url,
            detected_language=submission.detected_language,
            created_at=submission.created_at,
        ),
        overall_verdict=verification.overall_verdict,
        confidence_band=verification.confidence_band,
        summary=verification.summary,
        claims=claims,
        media_analyses=[
            MediaAnalysisResponse(
                kind=m.kind.value,
                manipulation_signals=m.manipulation_signals or [],
                metadata_captured_at=m.metadata_captured_at,
                earliest_known_appearance=m.earliest_known_appearance,
                predates_claimed_event=m.predates_claimed_event,
                ocr_status=m.ocr_status,
                ocr_text=m.ocr_text,
                ocr_unavailable_reason=m.ocr_unavailable_reason,
                corpus_matches=m.corpus_matches or [],
                analysis_availability=m.analysis_availability or {},
            )
            for m in verification.media_analyses
        ],
        total_evidence=total_evidence,
        supporting_evidence=supporting,
        contradicting_evidence=contradicting,
        independent_origins=sum(c.independent_origins for c in claims),
        unresolved_claims=unresolved,
        degraded=verification.degraded,
        degradation_reasons=verification.degradation_reasons or [],
        error_code=verification.error_code,
        error_message=verification.error_message,
        pipeline_version=verification.pipeline_version,
        scoring_version=verification.scoring_version,
        retrieval_version=verification.retrieval_version,
        confidence_score=verification.confidence_score,
        score_breakdown=verification.score_breakdown,
        stages=_stage_responses(verification),
        created_at=verification.created_at,
        completed_at=verification.completed_at,
    )


@router.get("/verifications/{public_id}/claims", response_model=list[ClaimResponse])
async def get_claims(
    public_id: str = Depends(validate_verification_id),
    session: AsyncSession = Depends(db_session),
) -> list[ClaimResponse]:
    """Claims with their per-claim verdicts."""
    verification = await _load_verification(session, public_id)
    return await _claim_responses(session, verification)


@router.get("/verifications/{public_id}/evidence", response_model=list[EvidenceResponse])
async def get_evidence(
    public_id: str = Depends(validate_verification_id),
    relationship: EvidenceRelationship | None = Query(default=None),
    session: AsyncSession = Depends(db_session),
) -> list[EvidenceResponse]:
    """Evidence, optionally filtered by relationship.

    Contradicting evidence is always available regardless of the overall
    verdict: hiding it would defeat the purpose of the product.
    """
    verification = await _load_verification(session, public_id)

    stmt = (
        select(Evidence)
        .join(Claim, Evidence.claim_id == Claim.id)
        .where(Claim.verification_id == verification.id)
        .options(selectinload(Evidence.document))
        .order_by(desc(Evidence.relevance_score))
    )
    if relationship is not None:
        stmt = stmt.where(Evidence.relationship_type == relationship)

    items = (await session.execute(stmt)).scalars().all()
    return [
        EvidenceResponse(
            relationship=ev.relationship_type,
            evidence_text=ev.evidence_text,
            document_title=ev.document.title if ev.document else None,
            document_url=(ev.document.canonical_url or ev.document.url) if ev.document else None,
            published_at=ev.document.published_at if ev.document else None,
            relevance_score=ev.relevance_score,
            cluster_id=ev.cluster_id,
        )
        for ev in items
    ]


@router.get("/recent", response_model=RecentListResponse)
async def get_recent(
    limit: int = Query(default=20, ge=1, le=50),
    verdict: Verdict | None = Query(default=None),
    status_filter: VerificationStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(db_session),
    _: None = Depends(rate_limit(RateLimitOperation.SEARCH)),
) -> RecentListResponse:
    """Recent public verifications.

    Real data only. When there are none, the list is empty -- the UI must show
    an honest empty state rather than invented activity.
    """
    stmt = (
        select(Verification)
        .options(selectinload(Verification.submission))
        .order_by(desc(Verification.created_at))
        .limit(limit)
    )
    if verdict is not None:
        stmt = stmt.where(Verification.overall_verdict == verdict)
    if status_filter is not None:
        stmt = stmt.where(Verification.status == status_filter)

    verifications = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(select(func.count(Verification.id)))).scalar_one()

    items = []
    for v in verifications:
        sub = v.submission
        excerpt = (sub.text or sub.caption or sub.submitted_url or "")[:280] or None
        items.append(
            RecentVerificationResponse(
                public_id=v.public_id,
                status=v.status,
                content_type=sub.content_type,
                title=sub.title,
                excerpt=excerpt,
                overall_verdict=v.overall_verdict,
                confidence_band=v.confidence_band,
                created_at=v.created_at,
                completed_at=v.completed_at,
            )
        )

    return RecentListResponse(items=items, total=total)
