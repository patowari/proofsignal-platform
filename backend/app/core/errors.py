"""Typed application errors.

Errors carry a stable machine-readable code so the API envelope and the frontend
can react without string-matching messages.

Design rule: an internal failure never becomes a substantive verdict. If we could
not check something, the pipeline records a failure with its reason -- it does not
quietly return FALSE. See .claude/rules/verification.md.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base for all application errors."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    #: Whether retrying the same operation could plausibly succeed. Drives the
    #: worker's retry decision: transient errors back off, deterministic ones fail fast.
    transient: bool = False

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_envelope(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


# ---- Client input ------------------------------------------------------


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    http_status = 400


class NotFoundError(AppError):
    code = "NOT_FOUND"
    http_status = 404


class RateLimitError(AppError):
    code = "RATE_LIMITED"
    http_status = 429

    def __init__(
        self, message: str, retry_after_seconds: int, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message, details)
        self.retry_after_seconds = retry_after_seconds


class PayloadTooLargeError(AppError):
    code = "PAYLOAD_TOO_LARGE"
    http_status = 413


class UnsupportedMediaTypeError(AppError):
    code = "UNSUPPORTED_MEDIA_TYPE"
    http_status = 415


# ---- Security ----------------------------------------------------------


class UnsafeURLError(ValidationError):
    """A URL was rejected by SSRF protection.

    The message is deliberately non-specific to the caller: telling an attacker
    exactly which internal range they hit is free reconnaissance.
    """

    code = "UNSAFE_URL"
    http_status = 400


class UnsafeUploadError(ValidationError):
    code = "UNSAFE_UPLOAD"
    http_status = 400


# ---- External dependencies ---------------------------------------------


class FetchError(AppError):
    code = "FETCH_FAILED"
    http_status = 502
    transient = True


class ContentUnavailableError(AppError):
    """Content exists but we cannot legitimately access it.

    Paywalled, login-gated, deleted, or platform-restricted. This is reported
    honestly to the user; we never pretend we retrieved it, and we never attempt
    to bypass the restriction.
    """

    code = "CONTENT_UNAVAILABLE"
    http_status = 422


class ProviderUnavailableError(AppError):
    """An optional provider (Ollama, OCR, embeddings) is not available.

    Callers degrade rather than fail wherever the pipeline allows it.
    """

    code = "PROVIDER_UNAVAILABLE"
    http_status = 503
    transient = True


class DependencyDownError(AppError):
    """A required dependency (PostgreSQL, Redis) is unreachable."""

    code = "DEPENDENCY_DOWN"
    http_status = 503
    transient = True


# ---- Processing --------------------------------------------------------


class AIOutputValidationError(AppError):
    """A model returned output that failed schema validation.

    Never coerce or partially accept malformed model output -- fail the stage.
    """

    code = "AI_OUTPUT_INVALID"
    http_status = 502
    transient = True


class MediaProcessingError(AppError):
    code = "MEDIA_PROCESSING_FAILED"
    http_status = 422


class StageFailedError(AppError):
    code = "STAGE_FAILED"
    http_status = 500

    def __init__(
        self,
        stage: str,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        transient: bool = False,
    ) -> None:
        super().__init__(message, {**(details or {}), "stage": stage})
        self.stage = stage
        self.transient = transient


class StorageError(AppError):
    code = "STORAGE_ERROR"
    http_status = 500
    transient = True
