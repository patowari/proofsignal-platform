"""SQLAlchemy models.

Imported here so Alembic autogenerate and Base.metadata see every table.
"""

from app.models.claim import Claim, ClaimEntity
from app.models.evidence import (
    ArticleIndex,
    Evidence,
    EvidenceCluster,
    RetrievedDocument,
    Source,
)
from app.models.media_analysis import MediaAnalysis, VideoTranscript
from app.models.retrieval import RetrievalQuery
from app.models.submission import MediaAsset, Submission
from app.models.verification import (
    Verification,
    VerificationRevision,
    VerificationStage,
)

__all__ = [
    "ArticleIndex",
    "Claim",
    "ClaimEntity",
    "Evidence",
    "EvidenceCluster",
    "MediaAnalysis",
    "MediaAsset",
    "RetrievalQuery",
    "RetrievedDocument",
    "Source",
    "Submission",
    "Verification",
    "VerificationRevision",
    "VerificationStage",
    "VideoTranscript",
]
