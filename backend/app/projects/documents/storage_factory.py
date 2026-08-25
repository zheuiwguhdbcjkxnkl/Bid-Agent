from __future__ import annotations

from minio import Minio

from app.core.config import Settings
from app.projects.documents.storage import (
    MinioObjectStorage,
    ObjectStorage,
    UnconfiguredObjectStorage,
)


def build_object_storage(settings: Settings) -> ObjectStorage:
    if (
        settings.minio_endpoint is None
        or settings.minio_access_key is None
        or settings.minio_secret_key is None
    ):
        return UnconfiguredObjectStorage()
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    return MinioObjectStorage(
        client=client,
        bucket_name=settings.minio_bucket_name,
    )
