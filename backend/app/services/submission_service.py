"""Submission intake.

Validate, store, create a verification, enqueue a job, return. Nothing expensive
happens on the request path -- the worker does all the real work.

Route handlers stay thin by delegating here; see .claude/rules/python.md.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    MediaKind,
    PipelineStage,
    SubmissionStatus,
    SubmissionType,
    VerificationStatus,
)
from app.core.ids import new_media_id, new_submission_id, new_verification_id
from app.core.logging import get_logger
from app.core.versions import PIPELINE_VERSION, RETRIEVAL_VERSION, SCORING_VERSION
from app.models import MediaAsset, Submission, Verification
from app.security.upload_validation import (
    ValidatedUpload,
    validate_image_upload,
    validate_video_upload,
)
from app.security.url_validation import validate_url
from app.services.storage import get_storage

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    submission_public_id: str
    verification_public_id: str
    status: VerificationStatus


def _content_hash(*parts: str | None) -> str:
    """Stable hash of normalized content, for dedup and caching."""
    joined = "\x1f".join((p or "").strip().lower() for p in parts)
    return hashlib.sha256(joined.encode()).hexdigest()


async def _create_verification(session: AsyncSession, submission: Submission) -> Verification:
    """Create the verification record in its initial queued state.

    Version stamps are captured now, at creation, so a result always records the
    code that actually produced it even if the process is upgraded mid-flight.
    """
    verification = Verification(
        public_id=new_verification_id(),
        submission=submission,
        status=VerificationStatus.QUEUED,
        current_stage=PipelineStage.QUEUED,
        pipeline_version=PIPELINE_VERSION,
        scoring_version=SCORING_VERSION,
        retrieval_version=RETRIEVAL_VERSION,
    )
    session.add(verification)
    return verification


async def create_text_submission(
    session: AsyncSession, *, text: str, title: str | None = None
) -> SubmissionResult:
    submission = Submission(
        public_id=new_submission_id(),
        content_type=SubmissionType.TEXT,
        status=SubmissionStatus.RECEIVED,
        title=title,
        text=text,
        content_hash=_content_hash(text, title),
    )
    session.add(submission)
    verification = await _create_verification(session, submission)
    await session.flush()

    logger.info(
        "submission.created",
        submission_id=submission.public_id,
        verification_id=verification.public_id,
        content_type=SubmissionType.TEXT.value,
        text_length=len(text),
    )
    return SubmissionResult(submission.public_id, verification.public_id, VerificationStatus.QUEUED)


async def create_url_submission(
    session: AsyncSession, *, url: str, note: str | None = None
) -> SubmissionResult:
    """Create a URL submission.

    The URL is structurally validated here so an obviously unsafe one is
    rejected synchronously with a clear error, rather than failing later inside
    a job the user has to wait for. The worker re-validates before fetching --
    validation at submission time is not a substitute for validation at fetch
    time, since DNS can change in between.
    """
    validated = validate_url(url)

    content_type = (
        SubmissionType.SOCIAL_URL if _is_social_url(validated.host) else SubmissionType.ARTICLE_URL
    )

    submission = Submission(
        public_id=new_submission_id(),
        content_type=content_type,
        status=SubmissionStatus.RECEIVED,
        submitted_url=url,
        caption=note,
        content_hash=_content_hash(url),
    )
    session.add(submission)
    verification = await _create_verification(session, submission)
    await session.flush()

    logger.info(
        "submission.created",
        submission_id=submission.public_id,
        verification_id=verification.public_id,
        content_type=content_type.value,
        url_host=validated.host,
    )
    return SubmissionResult(submission.public_id, verification.public_id, VerificationStatus.QUEUED)


#: Hosts we treat as social platforms. Routing only -- it decides which resolver
#: runs, and carries no judgement about the content's truthfulness.
_SOCIAL_HOSTS = (
    "facebook.com",
    "fb.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
    "reddit.com",
    "threads.net",
    "linkedin.com",
    "mastodon.social",
    "bsky.app",
)


def _is_social_url(host: str) -> bool:
    host = host.lower().removeprefix("www.")
    return any(host == h or host.endswith("." + h) for h in _SOCIAL_HOSTS)


async def _store_media(
    session: AsyncSession,
    submission: Submission,
    upload: ValidatedUpload,
    original_filename: str | None,
) -> MediaAsset:
    """Persist bytes to object storage and metadata to PostgreSQL.

    The storage key is generated; the user's filename is kept only as an inert
    display string and never touches a path.
    """
    storage = get_storage()
    storage.ensure_bucket()
    stored = storage.put(upload.content, content_type=upload.content_type, size=upload.size)

    asset = MediaAsset(
        public_id=new_media_id(),
        submission=submission,
        kind=upload.kind,
        storage_key=stored.key,
        storage_bucket=stored.bucket,
        mime_type=upload.content_type,
        byte_size=upload.size,
        sha256=hashlib.sha256(upload.content).hexdigest(),
        width=upload.width,
        height=upload.height,
        duration_seconds=upload.duration_seconds,
        original_filename=(original_filename or "")[:255] or None,
    )
    session.add(asset)
    return asset


async def create_image_submission(
    session: AsyncSession,
    *,
    data: bytes,
    declared_type: str | None,
    filename: str | None,
    caption: str | None = None,
    is_screenshot: bool = False,
) -> SubmissionResult:
    upload = validate_image_upload(data, declared_type=declared_type, is_screenshot=is_screenshot)

    if is_screenshot:
        content_type = SubmissionType.SCREENSHOT
    elif caption:
        content_type = SubmissionType.IMAGE_WITH_CAPTION
    else:
        content_type = SubmissionType.IMAGE

    submission = Submission(
        public_id=new_submission_id(),
        content_type=content_type,
        status=SubmissionStatus.RECEIVED,
        caption=caption,
        content_hash=hashlib.sha256(data).hexdigest(),
    )
    session.add(submission)
    await _store_media(session, submission, upload, filename)
    verification = await _create_verification(session, submission)
    await session.flush()

    logger.info(
        "submission.created",
        submission_id=submission.public_id,
        verification_id=verification.public_id,
        content_type=content_type.value,
        media_kind=upload.kind.value,
        size=upload.size,
    )
    return SubmissionResult(submission.public_id, verification.public_id, VerificationStatus.QUEUED)


async def create_video_submission(
    session: AsyncSession,
    *,
    data: bytes,
    declared_type: str | None,
    filename: str | None,
    caption: str | None = None,
) -> SubmissionResult:
    """Create a video submission.

    Signature and size are validated here. Duration and resolution require
    ffprobe against a file on disk and are enforced by the worker before any
    transcoding -- keeping the request path fast while still rejecting oversized
    media before expensive work begins.
    """
    upload = validate_video_upload(data, declared_type=declared_type)

    content_type = SubmissionType.VIDEO_WITH_CAPTION if caption else SubmissionType.VIDEO

    submission = Submission(
        public_id=new_submission_id(),
        content_type=content_type,
        status=SubmissionStatus.RECEIVED,
        caption=caption,
        content_hash=hashlib.sha256(data).hexdigest(),
    )
    session.add(submission)
    await _store_media(session, submission, upload, filename)
    verification = await _create_verification(session, submission)
    await session.flush()

    logger.info(
        "submission.created",
        submission_id=submission.public_id,
        verification_id=verification.public_id,
        content_type=content_type.value,
        size=upload.size,
    )
    return SubmissionResult(submission.public_id, verification.public_id, VerificationStatus.QUEUED)


def media_kind_for(submission: Submission) -> MediaKind | None:
    """The media kind implied by a submission type, if any."""
    mapping = {
        SubmissionType.IMAGE: MediaKind.IMAGE,
        SubmissionType.IMAGE_WITH_CAPTION: MediaKind.IMAGE,
        SubmissionType.SCREENSHOT: MediaKind.SCREENSHOT,
        SubmissionType.VIDEO: MediaKind.VIDEO,
        SubmissionType.VIDEO_WITH_CAPTION: MediaKind.VIDEO,
    }
    return mapping.get(submission.content_type)
