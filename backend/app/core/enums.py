"""Shared domain vocabulary.

These enums are the contract between the database, the API, and the frontend's
Zod schemas. Values are stable uppercase strings; renaming one is a breaking
change that requires a migration and a frontend update.
"""

from __future__ import annotations

from enum import StrEnum


class SubmissionType(StrEnum):
    """What kind of thing the visitor submitted."""

    TEXT = "TEXT"
    ARTICLE_URL = "ARTICLE_URL"
    SOCIAL_URL = "SOCIAL_URL"
    IMAGE = "IMAGE"
    SCREENSHOT = "SCREENSHOT"
    IMAGE_WITH_CAPTION = "IMAGE_WITH_CAPTION"
    VIDEO = "VIDEO"
    VIDEO_WITH_CAPTION = "VIDEO_WITH_CAPTION"

    @property
    def has_media(self) -> bool:
        return self in {
            SubmissionType.IMAGE,
            SubmissionType.SCREENSHOT,
            SubmissionType.IMAGE_WITH_CAPTION,
            SubmissionType.VIDEO,
            SubmissionType.VIDEO_WITH_CAPTION,
        }

    @property
    def is_video(self) -> bool:
        return self in {SubmissionType.VIDEO, SubmissionType.VIDEO_WITH_CAPTION}

    @property
    def is_url(self) -> bool:
        return self in {SubmissionType.ARTICLE_URL, SubmissionType.SOCIAL_URL}


class SubmissionStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class VerificationStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PipelineStage(StrEnum):
    """Ordered pipeline stages. The progress UI renders these directly."""

    QUEUED = "QUEUED"
    NORMALIZING = "NORMALIZING"
    EXTRACTING_CONTENT = "EXTRACTING_CONTENT"
    DETECTING_LANGUAGE = "DETECTING_LANGUAGE"
    EXTRACTING_CLAIMS = "EXTRACTING_CLAIMS"
    GENERATING_QUERIES = "GENERATING_QUERIES"
    RETRIEVING_EVIDENCE = "RETRIEVING_EVIDENCE"
    FETCHING_DOCUMENTS = "FETCHING_DOCUMENTS"
    EXTRACTING_EVIDENCE = "EXTRACTING_EVIDENCE"
    CLASSIFYING_EVIDENCE = "CLASSIFYING_EVIDENCE"
    ANALYZING_MEDIA = "ANALYZING_MEDIA"
    SCORING = "SCORING"
    GENERATING_REPORT = "GENERATING_REPORT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    @property
    def label(self) -> str:
        """Human-facing stage description shown in the progress UI."""
        return _STAGE_LABELS[self]


_STAGE_LABELS: dict[PipelineStage, str] = {
    PipelineStage.QUEUED: "Queued",
    PipelineStage.NORMALIZING: "Understanding content",
    PipelineStage.EXTRACTING_CONTENT: "Reading submission",
    PipelineStage.DETECTING_LANGUAGE: "Detecting language",
    PipelineStage.EXTRACTING_CLAIMS: "Extracting claims",
    PipelineStage.GENERATING_QUERIES: "Planning searches",
    PipelineStage.RETRIEVING_EVIDENCE: "Searching evidence",
    PipelineStage.FETCHING_DOCUMENTS: "Reading sources",
    PipelineStage.EXTRACTING_EVIDENCE: "Extracting evidence",
    PipelineStage.CLASSIFYING_EVIDENCE: "Cross-checking evidence",
    PipelineStage.ANALYZING_MEDIA: "Analyzing media",
    PipelineStage.SCORING: "Calculating result",
    PipelineStage.GENERATING_REPORT: "Preparing report",
    PipelineStage.COMPLETED: "Completed",
    PipelineStage.FAILED: "Failed",
}


class StageStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class Verdict(StrEnum):
    """Verdict taxonomy. See docs/PRODUCT.md.

    UNVERIFIED means we could not establish the claim either way. It is never a
    synonym for FALSE.
    """

    VERIFIED = "VERIFIED"
    LIKELY_TRUE = "LIKELY_TRUE"
    PARTLY_TRUE = "PARTLY_TRUE"
    MISLEADING = "MISLEADING"
    UNVERIFIED = "UNVERIFIED"
    LIKELY_FALSE = "LIKELY_FALSE"
    FALSE = "FALSE"
    SATIRE = "SATIRE"
    OPINION = "OPINION"

    @property
    def is_negative(self) -> bool:
        return self in {Verdict.FALSE, Verdict.LIKELY_FALSE, Verdict.MISLEADING}

    @property
    def is_positive(self) -> bool:
        return self in {Verdict.VERIFIED, Verdict.LIKELY_TRUE}

    @property
    def is_conclusive(self) -> bool:
        """Whether we reached a substantive finding at all."""
        return self is not Verdict.UNVERIFIED


class ConfidenceBand(StrEnum):
    """Confidence is shown as a band. Never a percentage."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ClaimType(StrEnum):
    EVENT = "EVENT"
    STATISTIC = "STATISTIC"
    QUOTE = "QUOTE"
    ATTRIBUTION = "ATTRIBUTION"
    CAUSAL = "CAUSAL"
    EXISTENCE = "EXISTENCE"
    IDENTITY = "IDENTITY"
    LOCATION = "LOCATION"
    TEMPORAL = "TEMPORAL"
    PREDICTION = "PREDICTION"
    OPINION = "OPINION"
    OTHER = "OTHER"

    @property
    def is_checkable(self) -> bool:
        """Predictions and opinions are not factually checkable against evidence."""
        return self not in {ClaimType.PREDICTION, ClaimType.OPINION}


class ClaimOrigin(StrEnum):
    """Where a claim came from.

    Origin is kept because an authentic video can carry a false user caption;
    the two must be verified and reported separately.
    """

    USER_TEXT = "USER_TEXT"
    USER_CAPTION = "USER_CAPTION"
    ARTICLE_TEXT = "ARTICLE_TEXT"
    SOCIAL_POST_TEXT = "SOCIAL_POST_TEXT"
    VIDEO_TRANSCRIPT = "VIDEO_TRANSCRIPT"
    ON_SCREEN_TEXT = "ON_SCREEN_TEXT"
    OCR_TEXT = "OCR_TEXT"


class EvidenceRelationship(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    NEUTRAL = "NEUTRAL"
    INSUFFICIENT = "INSUFFICIENT"


class SourceType(StrEnum):
    """Source category. One weighted feature -- never a truth oracle.

    We never hardcode a domain as trustworthy. See .claude/rules/verification.md.
    """

    OFFICIAL_GOVERNMENT = "OFFICIAL_GOVERNMENT"
    OFFICIAL_COMPANY = "OFFICIAL_COMPANY"
    PRIMARY_DOCUMENT = "PRIMARY_DOCUMENT"
    SCIENTIFIC_SOURCE = "SCIENTIFIC_SOURCE"
    NEWS_AGENCY = "NEWS_AGENCY"
    NEWS_ORGANIZATION = "NEWS_ORGANIZATION"
    SPECIALIST_PUBLICATION = "SPECIALIST_PUBLICATION"
    BLOG = "BLOG"
    SOCIAL_MEDIA = "SOCIAL_MEDIA"
    USER_PROVIDED = "USER_PROVIDED"
    UNKNOWN = "UNKNOWN"


class PenaltyType(StrEnum):
    """Context penalties: every fact checks out but the claim as framed misleads."""

    NUMERIC_MISMATCH = "NUMERIC_MISMATCH"
    DATE_MISMATCH = "DATE_MISMATCH"
    LOCATION_MISMATCH = "LOCATION_MISMATCH"
    ENTITY_MISMATCH = "ENTITY_MISMATCH"
    STALE_MEDIA = "STALE_MEDIA"
    EXAGGERATION = "EXAGGERATION"


class MediaKind(StrEnum):
    IMAGE = "IMAGE"
    SCREENSHOT = "SCREENSHOT"
    VIDEO = "VIDEO"


class AnalysisAvailability(StrEnum):
    """Whether a sub-analysis actually ran.

    UNAVAILABLE exists so a missing engine is never reported as a finding about
    the user's content: "no OCR engine installed" must never render as "no text
    found in the image".
    """

    COMPLETED = "COMPLETED"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class RetrievalProviderName(StrEnum):
    INDEXED_CORPUS = "INDEXED_CORPUS"
    GDELT = "GDELT"
    RSS_CORPUS = "RSS_CORPUS"
    DIRECT_URL = "DIRECT_URL"
    OFFICIAL_SOURCE = "OFFICIAL_SOURCE"
