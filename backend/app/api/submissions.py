"""Submission endpoints.

No authentication: V1 is anonymously usable by design.

Handlers stay thin -- validate, delegate to the service layer, enqueue, respond.
No business logic and no database queries live here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, rate_limit
from app.core.config import get_settings
from app.core.errors import PayloadTooLargeError
from app.core.logging import get_logger
from app.schemas.verification import (
    SubmissionAcceptedResponse,
    TextSubmissionRequest,
    UrlSubmissionRequest,
)
from app.services import submission_service
from app.services.rate_limit import RateLimitOperation
from app.workers.queue import get_queue

logger = get_logger(__name__)

router = APIRouter(prefix="/submissions", tags=["submissions"])


def _accepted(result: submission_service.SubmissionResult) -> SubmissionAcceptedResponse:
    """Enqueue the verification job and build the response.

    Enqueueing happens after the database work so a job never references a
    record that was rolled back.
    """
    get_queue().enqueue({"verification_public_id": result.verification_public_id})
    return SubmissionAcceptedResponse(
        submission_public_id=result.submission_public_id,
        verification_public_id=result.verification_public_id,
        status=result.status,
        poll_url=f"/api/verifications/{result.verification_public_id}/status",
    )


async def _read_upload(upload: UploadFile, max_bytes: int, label: str) -> bytes:
    """Read an upload, enforcing the size cap while streaming.

    Reading the whole body first would let an oversized file exhaust memory
    before any check ran, so the cap is applied as chunks arrive.
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(1024 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise PayloadTooLargeError(
                f"This {label} is larger than the maximum allowed size.",
                {"max_bytes": max_bytes},
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/text",
    response_model=SubmissionAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(RateLimitOperation.TEXT_SUBMISSION))],
)
async def submit_text(
    payload: TextSubmissionRequest,
    session: AsyncSession = Depends(db_session),
) -> SubmissionAcceptedResponse:
    """Submit a written claim or article text for verification."""
    result = await submission_service.create_text_submission(
        session, text=payload.text, title=payload.title
    )
    return _accepted(result)


@router.post(
    "/url",
    response_model=SubmissionAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(RateLimitOperation.URL_SUBMISSION))],
)
async def submit_url(
    payload: UrlSubmissionRequest,
    session: AsyncSession = Depends(db_session),
) -> SubmissionAcceptedResponse:
    """Submit an article or public social-media URL.

    The URL passes SSRF validation here; the worker re-validates before
    fetching, because DNS can change in between.
    """
    result = await submission_service.create_url_submission(
        session, url=payload.url, note=payload.note
    )
    return _accepted(result)


@router.post(
    "/image",
    response_model=SubmissionAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(RateLimitOperation.IMAGE_SUBMISSION))],
)
async def submit_image(
    file: UploadFile = File(...),
    caption: str | None = Form(default=None),
    is_screenshot: bool = Form(default=False),
    session: AsyncSession = Depends(db_session),
) -> SubmissionAcceptedResponse:
    """Submit an image or screenshot, optionally with the caption it circulated with."""
    settings = get_settings()
    data = await _read_upload(file, settings.max_image_bytes, "image")

    result = await submission_service.create_image_submission(
        session,
        data=data,
        declared_type=file.content_type,
        filename=file.filename,
        caption=caption,
        is_screenshot=is_screenshot,
    )
    return _accepted(result)


@router.post(
    "/video",
    response_model=SubmissionAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(RateLimitOperation.VIDEO_SUBMISSION))],
)
async def submit_video(
    file: UploadFile = File(...),
    caption: str | None = Form(default=None),
    session: AsyncSession = Depends(db_session),
) -> SubmissionAcceptedResponse:
    """Submit a video, optionally with the caption it circulated with."""
    settings = get_settings()
    data = await _read_upload(file, settings.max_video_bytes, "video")

    result = await submission_service.create_video_submission(
        session,
        data=data,
        declared_type=file.content_type,
        filename=file.filename,
        caption=caption,
    )
    return _accepted(result)
