"""Shared test fixtures.

The default suite runs offline with no Docker: fakeredis stands in for Redis and
an in-memory stub for object storage. Tests needing real services are marked
`integration`.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Generator
from typing import Any

import pytest

# psycopg's async mode cannot drive Windows' default ProactorEventLoop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Generator[None, None, None]:
    """Clear cached settings around each test.

    Settings are lru_cached, so a monkeypatched env var would otherwise leak
    into unrelated tests.
    """
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def fake_redis():  # type: ignore[no-untyped-def]
    """In-memory Redis, so queue logic is testable without Docker."""
    import fakeredis

    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def job_queue(fake_redis):  # type: ignore[no-untyped-def]
    from app.workers.queue import JobQueue

    return JobQueue(name="test-queue", redis_client=fake_redis)


class InMemoryStorage:
    """Object storage stub.

    Mirrors the S3ObjectStorage interface so services under test exercise the
    same code path they use in production.
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.bucket = "test-bucket"

    def ensure_bucket(self) -> None:
        return None

    def put(self, data: bytes, *, content_type: str, size: int) -> Any:
        from app.services.storage import StoredObject, generate_storage_key

        key = generate_storage_key(content_type)
        self.objects[key] = data
        return StoredObject(key=key, bucket=self.bucket, size=size, content_type=content_type)

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self.objects

    def presigned_url(self, key: str, *, expires_in: int = 3600) -> str:
        return f"memory://{self.bucket}/{key}"

    def health(self) -> dict[str, str]:
        return {"status": "ok", "bucket": self.bucket}


@pytest.fixture
def memory_storage(monkeypatch: pytest.MonkeyPatch) -> InMemoryStorage:
    storage = InMemoryStorage()
    monkeypatch.setattr("app.services.storage.get_storage", lambda: storage)
    monkeypatch.setattr("app.services.submission_service.get_storage", lambda: storage)
    return storage


@pytest.fixture
def png_bytes() -> bytes:
    """A real 8x8 PNG."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (100, 140, 200)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def jpeg_bytes() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (200, 100, 60)).save(buf, format="JPEG")
    return buf.getvalue()
