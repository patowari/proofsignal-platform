"""Object storage.

An S3-compatible abstraction: MinIO locally, S3 or any compatible service in
production, with no code change.

Large binaries live here; only metadata goes in PostgreSQL. Storage keys are
always generated -- a user's filename is never used to build a path, which
closes path traversal. See docs/SECURITY.md.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, BinaryIO, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.core.errors import StorageError
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Extensions we will ever write, mapped from the MIME type we detected from the
#: file's own signature -- never from the client's claim or filename.
_EXTENSION_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
    "video/x-matroska": "mkv",
}


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    bucket: str
    size: int
    content_type: str


class ObjectStorage(Protocol):
    """Storage interface. Swap implementations without touching domain code."""

    def put(self, data: bytes | BinaryIO, *, content_type: str, size: int) -> StoredObject: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def presigned_url(self, key: str, *, expires_in: int = 3600) -> str: ...


def generate_storage_key(content_type: str, *, prefix: str = "media") -> str:
    """Build a storage key from a UUID and the detected type.

    Deliberately ignores the user's filename entirely. Date-partitioned so a
    bucket listing stays navigable and lifecycle rules can target old objects.
    """
    extension = _EXTENSION_BY_MIME.get(content_type, "bin")
    today = date.today()
    return f"{prefix}/{today:%Y/%m/%d}/{uuid.uuid4().hex}.{extension}"


class S3ObjectStorage:
    """S3-compatible storage backed by boto3."""

    def __init__(self, bucket: str | None = None) -> None:
        settings = get_settings()
        self.bucket = bucket or settings.minio_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name=settings.minio_region,
            config=Config(
                signature_version="s3v4",
                # MinIO requires path-style addressing; virtual-host style
                # assumes DNS per bucket.
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=30,
            ),
        )

    def ensure_bucket(self) -> None:
        """Create the bucket if absent. Safe to call repeatedly."""
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in ("404", "NoSuchBucket", "403"):
                raise StorageError(f"Could not check bucket: {exc}") from exc
            try:
                self._client.create_bucket(Bucket=self.bucket)
                logger.info("storage.bucket_created", bucket=self.bucket)
            except ClientError as create_exc:
                # A concurrent worker may have won the race; that is fine.
                if create_exc.response.get("Error", {}).get("Code") not in (
                    "BucketAlreadyOwnedByYou",
                    "BucketAlreadyExists",
                ):
                    raise StorageError(f"Could not create bucket: {create_exc}") from create_exc

    def put(self, data: bytes | BinaryIO, *, content_type: str, size: int) -> StoredObject:
        key = generate_storage_key(content_type)
        try:
            body = data if isinstance(data, bytes) else data.read()
            self._client.put_object(
                Bucket=self.bucket, Key=key, Body=body, ContentType=content_type
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Could not store the uploaded file.") from exc
        logger.info("storage.put", key=key, size=size, content_type=content_type)
        return StoredObject(key=key, bucket=self.bucket, size=size, content_type=content_type)

    def get(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()  # type: ignore[no-any-return]
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"Could not read object: {key}") from exc

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"Could not delete object: {key}") from exc

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def presigned_url(self, key: str, *, expires_in: int = 3600) -> str:
        try:
            return self._client.generate_presigned_url(  # type: ignore[no-any-return]
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"Could not sign URL for: {key}") from exc

    def health(self) -> dict[str, Any]:
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return {"status": "ok", "bucket": self.bucket}
        except (BotoCoreError, ClientError) as exc:
            return {"status": "error", "bucket": self.bucket, "error": type(exc).__name__}


_storage: S3ObjectStorage | None = None


def get_storage() -> S3ObjectStorage:
    global _storage
    if _storage is None:
        _storage = S3ObjectStorage()
    return _storage
