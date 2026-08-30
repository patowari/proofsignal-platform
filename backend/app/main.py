"""FastAPI application.

Run with:

    uvicorn app.main:app --reload
"""

from __future__ import annotations

# Must precede any event-loop or database import: psycopg's async mode cannot
# drive Windows' default ProactorEventLoop.
from app.core.runtime import configure_event_loop

configure_event_loop()

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import health, submissions, verifications
from app.core.config import get_settings
from app.core.errors import AppError, RateLimitError
from app.core.logging import configure_logging, get_logger, request_id_var
from app.core.versions import API_VERSION

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    settings = get_settings()
    logger.info("api.starting", environment=settings.environment, version=API_VERSION)

    # Ensure the media bucket exists so the first upload does not fail. Storage
    # being unreachable at boot is logged, not fatal: /ready reports it, and the
    # API can still serve reads.
    try:
        from app.services.storage import get_storage

        get_storage().ensure_bucket()
    except Exception as exc:
        logger.warning("api.storage_unavailable", error_type=type(exc).__name__)

    yield
    logger.info("api.stopping")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Evidence-Backed Verification API",
        description=(
            "Submit a claim, URL, image, or video and receive an evidence-backed "
            "verification. No authentication: submissions are anonymous and public."
        ),
        version=API_VERSION,
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,  # no auth, so no credentialed requests
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "X-Request-Id"],
        # Lets the browser read the correlation id, so a user-reported problem
        # can be traced to its log line.
        expose_headers=["X-Request-Id", "Retry-After"],
        max_age=3600,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Attach a request id and log the outcome.

        The id is echoed in the response header so a user-reported problem can
        be traced to its log line.
        """
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request_id_var.set(request_id)

        import time

        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request.unhandled",
                method=request.method,
                path=request.url.path,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            raise

        duration_ms = int((time.monotonic() - started) * 1000)
        response.headers["x-request-id"] = request_id

        # Health polling would otherwise dominate the logs.
        if not request.url.path.endswith(("/health", "/ready")):
            logger.info(
                "request.completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
        return response

    # ---- Error handling -------------------------------------------------
    # One envelope shape for every error, so the frontend never has to guess.

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        headers = {}
        if isinstance(exc, RateLimitError):
            headers["Retry-After"] = str(exc.retry_after_seconds)

        logger.warning(
            "request.app_error", code=exc.code, status=exc.http_status, message=exc.message
        )
        return JSONResponse(status_code=exc.http_status, content=exc.to_envelope(), headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic puts the original exception object in "ctx", which is not
        # JSON-serializable; passing errors() through verbatim turns a 422 into
        # a 500. Keep only the fields a client can act on.
        fields = [
            {
                "field": ".".join(str(p) for p in err.get("loc", ())),
                "message": err.get("msg", "invalid value"),
                "type": err.get("type", "value_error"),
            }
            for err in exc.errors()[:10]
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "The request could not be processed as submitted.",
                    "details": {"fields": fields},
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
        # Never leak internals to a client; the detail is in the logs.
        logger.error("request.unhandled_error", error_type=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Something went wrong while processing this request.",
                    "details": {},
                }
            },
        )

    prefix = settings.api_prefix
    app.include_router(health.router, prefix=prefix)
    app.include_router(submissions.router, prefix=prefix)
    app.include_router(verifications.router, prefix=prefix)

    return app


app = create_app()
