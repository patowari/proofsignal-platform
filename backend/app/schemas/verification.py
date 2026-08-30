"""API request and response schemas.

These are the contract with the frontend. Enum values are mirrored in the
frontend's Zod schemas; changing one is a breaking change.

Serial database ids never appear here -- only opaque public ids.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import (
    AnalysisAvailability,
    ClaimOrigin,
    ClaimType,
    ConfidenceBand,
    EvidenceRelationship,
    PipelineStage,
    SourceType,
    SubmissionType,
    Verdict,
    VerificationStatus,
)

# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class TextSubmissionRequest(BaseModel):
    text: str = Field(min_length=10, max_length=50_000)
    title: str | None = Field(default=None, max_length=500)

    @field_validator("text")
    @classmethod
    def _must_have_content(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be blank")
        return v.strip()


class UrlSubmissionRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("url")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class SubmissionAcceptedResponse(BaseModel):
    """Returned immediately on submission.

    The request never waits for verification: it validates, stores, enqueues,
    and hands back an id to poll.
    """

    submission_public_id: str
    verification_public_id: str
    status: VerificationStatus
    poll_url: str


class StageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: PipelineStage
    #: Human-facing description, shown directly in the progress UI.
    label: str
    status: str
    sequence: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error_type: str | None = None


class VerificationStatusResponse(BaseModel):
    """The cheap endpoint the progress UI polls.

    Reads real VerificationStage rows, so displayed progress cannot drift from
    what the worker is actually doing.
    """

    public_id: str
    status: VerificationStatus
    current_stage: PipelineStage
    current_stage_label: str
    stage_index: int
    stage_count: int
    stages: list[StageResponse]
    degraded: bool = False
    degradation_reasons: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    relationship: EvidenceRelationship
    #: Minimum excerpt needed to justify the verdict -- never a full article.
    evidence_text: str
    source_name: str | None = None
    source_domain: str | None = None
    source_type: SourceType = SourceType.UNKNOWN
    document_title: str | None = None
    document_url: str | None = None
    published_at: datetime | None = None
    relevance_score: float = 0.0
    #: Groups syndicated copies. Two items sharing this are one origin, and the
    #: UI says so rather than presenting them as independent corroboration.
    cluster_id: int | None = None


class ClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    claim_text: str
    normalized_claim: str | None = None
    language: str = "en"
    claim_type: ClaimType
    origin: ClaimOrigin
    importance: float
    sequence: int
    verdict: Verdict | None = None
    confidence_band: ConfidenceBand | None = None
    evidence: list[EvidenceResponse] = Field(default_factory=list)
    supporting_count: int = 0
    contradicting_count: int = 0
    independent_origins: int = 0


class MediaAnalysisResponse(BaseModel):
    """Media findings.

    Integrity and context are separate fields on purpose: an authentic file can
    carry a false claim, and merging them into one score destroys that case.
    """

    model_config = ConfigDict(from_attributes=True)

    kind: str
    manipulation_signals: list[dict] = Field(default_factory=list)
    metadata_captured_at: datetime | None = None
    earliest_known_appearance: datetime | None = None
    predates_claimed_event: bool | None = None
    ocr_status: AnalysisAvailability = AnalysisAvailability.SKIPPED
    ocr_text: str | None = None
    ocr_unavailable_reason: str | None = None
    corpus_matches: list[dict] = Field(default_factory=list)
    analysis_availability: dict = Field(default_factory=dict)


class SubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: str
    content_type: SubmissionType
    title: str | None = None
    text: str | None = None
    caption: str | None = None
    submitted_url: str | None = None
    detected_language: str | None = None
    created_at: datetime


class SourceCheckedResponse(BaseModel):
    """A source we actually queried.

    Backed by the retrieval query log, so "sources checked" is auditable rather
    than asserted.
    """

    domain: str | None = None
    name: str | None = None
    source_type: SourceType = SourceType.UNKNOWN
    documents_found: int = 0


class VerificationReportResponse(BaseModel):
    """The full report."""

    public_id: str
    status: VerificationStatus
    submission: SubmissionResponse

    overall_verdict: Verdict | None = None
    confidence_band: ConfidenceBand | None = None
    summary: str | None = None

    claims: list[ClaimResponse] = Field(default_factory=list)
    media_analyses: list[MediaAnalysisResponse] = Field(default_factory=list)
    sources_checked: list[SourceCheckedResponse] = Field(default_factory=list)

    #: Counts after origin clustering, so the UI never presents N syndicated
    #: copies as N independent confirmations.
    total_evidence: int = 0
    supporting_evidence: int = 0
    contradicting_evidence: int = 0
    independent_origins: int = 0
    unresolved_claims: int = 0

    degraded: bool = False
    degradation_reasons: list[str] = Field(default_factory=list)
    #: Present when the pipeline failed. A failure is reported as a failure --
    #: it is never rendered as a substantive verdict.
    error_code: str | None = None
    error_message: str | None = None

    pipeline_version: str
    scoring_version: str
    retrieval_version: str
    #: Debug-only. The UI shows the band, never a percentage.
    confidence_score: float | None = None
    score_breakdown: dict | None = None

    stages: list[StageResponse] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None


class RecentVerificationResponse(BaseModel):
    """Compact row for listings."""

    model_config = ConfigDict(from_attributes=True)

    public_id: str
    status: VerificationStatus
    content_type: SubmissionType
    title: str | None = None
    excerpt: str | None = None
    overall_verdict: Verdict | None = None
    confidence_band: ConfidenceBand | None = None
    created_at: datetime
    completed_at: datetime | None = None


class RecentListResponse(BaseModel):
    items: list[RecentVerificationResponse]
    next_cursor: str | None = None
    total: int | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


class DependencyStatus(BaseModel):
    name: str
    status: str
    #: Required dependencies make the service unhealthy; optional ones only
    #: degrade it. The distinction is what keeps a missing Ollama from looking
    #: like an outage.
    required: bool
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: str
    dependencies: list[DependencyStatus]
    degraded_capabilities: list[str] = Field(default_factory=list)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail
