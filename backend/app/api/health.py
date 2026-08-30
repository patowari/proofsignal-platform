"""Health and readiness.

The distinction matters operationally: /health says the process is alive,
/ready says whether it can do useful work and what it currently cannot do.

Required dependencies (PostgreSQL, Redis) failing makes the service unhealthy.
Optional ones (Ollama, OCR) only degrade it -- reporting a missing Ollama as an
outage would be wrong, since the pipeline is designed to run without it.
"""

from __future__ import annotations

import shutil

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.versions import API_VERSION
from app.db.session import get_async_engine
from app.schemas.verification import (
    DependencyStatus,
    HealthResponse,
    ReadinessResponse,
)

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness. Deliberately does no I/O."""
    settings = get_settings()
    return HealthResponse(status="ok", version=API_VERSION, environment=settings.environment)


async def _check_database() -> DependencyStatus:
    try:
        engine = get_async_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return DependencyStatus(name="postgresql", status="ok", required=True)
    except Exception as exc:
        return DependencyStatus(
            name="postgresql", status="error", required=True, detail=type(exc).__name__
        )


async def _check_redis() -> DependencyStatus:
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(get_settings().redis_url)
        await client.ping()
        await client.aclose()
        return DependencyStatus(name="redis", status="ok", required=True)
    except Exception as exc:
        return DependencyStatus(
            name="redis", status="error", required=True, detail=type(exc).__name__
        )


def _check_storage() -> DependencyStatus:
    try:
        from app.services.storage import get_storage

        result = get_storage().health()
        return DependencyStatus(
            name="object_storage",
            status=result["status"],
            required=True,
            detail=result.get("error"),
        )
    except Exception as exc:
        return DependencyStatus(
            name="object_storage", status="error", required=True, detail=type(exc).__name__
        )


async def _check_ollama() -> DependencyStatus:
    """Optional. Absent Ollama degrades claim extraction to rule-based."""
    settings = get_settings()
    if not settings.ollama_enabled:
        return DependencyStatus(
            name="ollama", status="disabled", required=False, detail="disabled by configuration"
        )
    try:
        import httpx

        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")
            if response.status_code == 200:
                return DependencyStatus(name="ollama", status="ok", required=False)
            return DependencyStatus(
                name="ollama",
                status="unavailable",
                required=False,
                detail=f"HTTP {response.status_code}",
            )
    except Exception:
        return DependencyStatus(
            name="ollama", status="unavailable", required=False, detail="not reachable"
        )


def _check_binary(name: str, path: str) -> DependencyStatus:
    found = shutil.which(path) is not None
    return DependencyStatus(
        name=name,
        status="ok" if found else "unavailable",
        required=False,
        detail=None if found else f"{path} not found on PATH",
    )


@router.get("/ready", response_model=ReadinessResponse)
async def ready() -> ReadinessResponse:
    """Readiness with per-dependency detail."""
    settings = get_settings()

    dependencies = [
        await _check_database(),
        await _check_redis(),
        _check_storage(),
        await _check_ollama(),
        _check_binary("ffmpeg", settings.ffmpeg_path),
        _check_binary("ffprobe", settings.ffprobe_path),
        _check_binary("tesseract", settings.tesseract_path),
    ]

    required_down = [d for d in dependencies if d.required and d.status != "ok"]
    optional_down = [d for d in dependencies if not d.required and d.status != "ok"]

    # Name the concrete capability lost, so the report and the operator both
    # learn something more useful than "a dependency is down".
    capability_by_dependency = {
        "ollama": "AI-assisted claim extraction (falls back to rule-based)",
        "tesseract": "OCR for images and screenshots",
        "ffmpeg": "video processing",
        "ffprobe": "video metadata inspection",
    }
    degraded = [
        capability_by_dependency.get(d.name, d.name)
        for d in optional_down
        if d.status != "disabled"
    ]

    return ReadinessResponse(
        status="not_ready" if required_down else ("degraded" if degraded else "ready"),
        dependencies=dependencies,
        degraded_capabilities=degraded,
    )
