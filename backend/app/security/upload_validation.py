"""Upload validation.

Every upload is hostile until proven otherwise. The client's declared
content-type and filename are claims, not facts: we determine the real type from
the file's own bytes and reject any disagreement.

Threat model: docs/SECURITY.md.
"""

from __future__ import annotations

import io
import subprocess
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.enums import MediaKind
from app.core.errors import (
    MediaProcessingError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Magic-byte signatures. The offset matters: ISO-BMFF containers (MP4/MOV)
#: carry their brand at byte 4, after the box size.
_IMAGE_SIGNATURES: tuple[tuple[int, bytes, str], ...] = (
    (0, b"\xff\xd8\xff", "image/jpeg"),
    (0, b"\x89PNG\r\n\x1a\n", "image/png"),
    (0, b"GIF87a", "image/gif"),
    (0, b"GIF89a", "image/gif"),
    (0, b"RIFF", "image/webp"),  # confirmed by the WEBP tag at offset 8
)

_VIDEO_SIGNATURES: tuple[tuple[int, bytes, str], ...] = (
    (4, b"ftypmp4", "video/mp4"),
    (4, b"ftypisom", "video/mp4"),
    (4, b"ftypiso2", "video/mp4"),
    (4, b"ftypavc1", "video/mp4"),
    (4, b"ftypmmp4", "video/mp4"),
    (4, b"ftypM4V", "video/mp4"),
    (4, b"ftypqt", "video/quicktime"),
    (0, b"\x1a\x45\xdf\xa3", "video/webm"),  # EBML: WebM and Matroska
)

ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})
ALLOWED_VIDEO_TYPES = frozenset({"video/mp4", "video/quicktime", "video/webm", "video/x-matroska"})


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    """An upload that passed validation."""

    content: bytes
    #: The type determined from the file's bytes -- not what the client claimed.
    content_type: str
    kind: MediaKind
    size: int
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None


def detect_content_type(data: bytes) -> str | None:
    """Identify a file from its signature bytes."""
    if len(data) < 12:
        return None

    for offset, signature, mime in _IMAGE_SIGNATURES:
        if data[offset : offset + len(signature)] == signature:
            # RIFF alone is ambiguous (WebP, WAV, AVI); confirm the WEBP tag.
            if signature == b"RIFF":
                if data[8:12] == b"WEBP":
                    return "image/webp"
                continue
            return mime

    for offset, signature, mime in _VIDEO_SIGNATURES:
        if data[offset : offset + len(signature)] == signature:
            return mime

    return None


def _reject_polyglot(data: bytes) -> None:
    """Reject files that are valid in two formats at once.

    A GIF that is also valid HTML will be served as an image by us and executed
    as a script by a browser that sniffs it. The header is where such payloads
    have to live, so that is where we look.
    """
    header = data[:2048].lower()
    for marker in (b"<html", b"<script", b"<?php", b"<%", b"<!doctype html", b"<svg"):
        if marker in header:
            raise UnsupportedMediaTypeError(
                "This file appears to contain markup or script content and cannot be processed.",
                {"reason": "polyglot_detected"},
            )


def validate_image_upload(
    data: bytes, *, declared_type: str | None = None, is_screenshot: bool = False
) -> ValidatedUpload:
    """Validate an image upload.

    Raises PayloadTooLargeError, UnsupportedMediaTypeError, or
    MediaProcessingError.
    """
    settings = get_settings()

    if not data:
        raise UnsupportedMediaTypeError("The uploaded file is empty.")

    if len(data) > settings.max_image_bytes:
        raise PayloadTooLargeError(
            "This image is larger than the maximum allowed size.",
            {"size": len(data), "max_bytes": settings.max_image_bytes},
        )

    detected = detect_content_type(data)
    if detected is None or detected not in ALLOWED_IMAGE_TYPES:
        raise UnsupportedMediaTypeError(
            "This file is not a supported image format (JPEG, PNG, GIF, or WebP).",
            {"detected": detected, "declared": declared_type},
        )

    # A mismatch means the client lied about the type or the file is a polyglot.
    # Either way we do not proceed on a guess.
    if declared_type and declared_type.split(";")[0].strip().lower() not in (
        detected,
        "application/octet-stream",
    ):
        raise UnsupportedMediaTypeError(
            "The file content does not match its declared type.",
            {"detected": detected, "declared": declared_type},
        )

    _reject_polyglot(data)

    width, height = _probe_image_dimensions(data)

    return ValidatedUpload(
        content=data,
        content_type=detected,
        kind=MediaKind.SCREENSHOT if is_screenshot else MediaKind.IMAGE,
        size=len(data),
        width=width,
        height=height,
    )


def _probe_image_dimensions(data: bytes) -> tuple[int | None, int | None]:
    """Read dimensions, guarding against decompression bombs.

    Pillow reads the header without decoding pixels, so a bomb is rejected
    before it can allocate gigabytes.
    """
    settings = get_settings()
    try:
        from PIL import Image

        # Enforce our own cap rather than Pillow's default warning threshold.
        Image.MAX_IMAGE_PIXELS = settings.max_image_pixels

        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size

            if width > settings.max_image_dimension or height > settings.max_image_dimension:
                raise PayloadTooLargeError(
                    "This image's dimensions exceed the maximum allowed.",
                    {
                        "width": width,
                        "height": height,
                        "max_dimension": settings.max_image_dimension,
                    },
                )
            if width * height > settings.max_image_pixels:
                raise PayloadTooLargeError(
                    "This image contains too many pixels to process safely.",
                    {"pixels": width * height, "max_pixels": settings.max_image_pixels},
                )
            return width, height

    except (PayloadTooLargeError, UnsupportedMediaTypeError):
        raise
    except Image.DecompressionBombError as exc:  # type: ignore[name-defined]
        raise PayloadTooLargeError(
            "This image appears to be a decompression bomb.", {"error": str(exc)}
        ) from exc
    except Exception as exc:
        raise MediaProcessingError(
            "This image could not be read. It may be corrupted.",
            {"error_type": type(exc).__name__},
        ) from exc


def validate_video_upload(data: bytes, *, declared_type: str | None = None) -> ValidatedUpload:
    """Validate a video upload.

    Size and signature are checked here; duration and resolution need ffprobe
    and are checked by probe_video_metadata once the bytes are on disk. Both
    happen before any transcoding.
    """
    settings = get_settings()

    if not data:
        raise UnsupportedMediaTypeError("The uploaded file is empty.")

    if len(data) > settings.max_video_bytes:
        raise PayloadTooLargeError(
            "This video is larger than the maximum allowed size.",
            {"size": len(data), "max_bytes": settings.max_video_bytes},
        )

    detected = detect_content_type(data)
    if detected is None or detected not in ALLOWED_VIDEO_TYPES:
        raise UnsupportedMediaTypeError(
            "This file is not a supported video format (MP4, MOV, WebM, or MKV).",
            {"detected": detected, "declared": declared_type},
        )

    _reject_polyglot(data)

    return ValidatedUpload(
        content=data,
        content_type=detected,
        kind=MediaKind.VIDEO,
        size=len(data),
    )


def probe_video_metadata(file_path: str) -> dict[str, float | int | str | None]:
    """Read video metadata with ffprobe and enforce limits.

    Called before any transcoding, so an oversized or malformed file is rejected
    cheaply.

    Security: argv list with shell=False, so no user value can reach a shell. The
    path is one we generated, never a user filename.
    """
    settings = get_settings()

    command = [
        settings.ffprobe_path,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        # Explicitly terminate option parsing so a path starting with "-" can
        # never be read as a flag.
        "-i",
        file_path,
    ]

    try:
        result = subprocess.run(  # noqa: S603 - argv list, shell=False, fixed binary
            command,
            capture_output=True,
            timeout=30,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaProcessingError(
            "Reading this video timed out. It may be corrupted.", {"timeout": 30}
        ) from exc
    except FileNotFoundError as exc:
        raise MediaProcessingError(
            "Video processing is unavailable: ffprobe was not found.",
            {"ffprobe_path": settings.ffprobe_path},
        ) from exc

    if result.returncode != 0:
        raise MediaProcessingError(
            "This video could not be read. It may be corrupted or use an unsupported codec.",
            {"returncode": result.returncode},
        )

    import json

    try:
        probe = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaProcessingError("Video metadata could not be parsed.") from exc

    fmt = probe.get("format", {})
    streams = probe.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]

    if not video_streams:
        raise MediaProcessingError("This file contains no video stream.")

    try:
        duration = float(fmt.get("duration", 0.0))
    except (TypeError, ValueError):
        duration = 0.0

    if duration > settings.max_video_duration_seconds:
        raise PayloadTooLargeError(
            "This video is longer than the maximum allowed duration.",
            {"duration": duration, "max_duration": settings.max_video_duration_seconds},
        )

    primary = video_streams[0]
    width = int(primary.get("width") or 0)
    height = int(primary.get("height") or 0)

    if max(width, height) > settings.max_video_resolution:
        raise PayloadTooLargeError(
            "This video's resolution is higher than the maximum allowed.",
            {
                "width": width,
                "height": height,
                "max_resolution": settings.max_video_resolution,
            },
        )

    return {
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "codec": primary.get("codec_name"),
        "format": fmt.get("format_name"),
        "bit_rate": fmt.get("bit_rate"),
        "stream_count": len(streams),
    }
