"""Structured logging.

Never log secrets, tokens, credentials, raw client IPs, or binary payloads.
See .claude/rules/security.md.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

from app.core.config import get_settings

#: Correlation ids bound for the lifetime of a request or job, so every log line
#: emitted downstream can be tied back without threading a logger through calls.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
verification_id_var: ContextVar[str | None] = ContextVar("verification_id", default=None)
job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)

#: Keys scrubbed from log output wherever they appear.
_REDACTED_KEYS = frozenset(
    {
        "password", "secret", "token", "api_key", "apikey", "authorization",
        "cookie", "access_key", "secret_key", "minio_secret_key",
        "client_fingerprint_salt", "ip", "ip_address", "client_ip",
    }
)


def _add_correlation_ids(
    _logger: Any, _method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    for key, var in (
        ("request_id", request_id_var),
        ("verification_id", verification_id_var),
        ("job_id", job_id_var),
    ):
        value = var.get()
        if value is not None:
            event_dict.setdefault(key, value)
    return event_dict


def _redact(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Drop sensitive keys and truncate anything large enough to be a payload."""
    for key in list(event_dict):
        if key.lower() in _REDACTED_KEYS:
            event_dict[key] = "[redacted]"
        elif isinstance(event_dict[key], bytes):
            event_dict[key] = f"[{len(event_dict[key])} bytes]"
        elif isinstance(event_dict[key], str) and len(event_dict[key]) > 2000:
            event_dict[key] = event_dict[key][:2000] + "...[truncated]"
    return event_dict


def configure_logging() -> None:
    settings = get_settings()

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _add_correlation_ids,
        _redact,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=settings.log_level.upper())
    # Uvicorn's access log duplicates our request middleware log line.
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)
