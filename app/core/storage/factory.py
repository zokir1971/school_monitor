# app/core/storage/factory.py (Фабрика должна возвращать singleton)

from functools import lru_cache

from app.core.config import get_settings
from app.core.storage.base import BaseStorage
from app.core.storage.local import LocalStorage
from app.core.storage.s3 import S3Storage


@lru_cache(maxsize=1)
def get_storage() -> BaseStorage:
    settings = get_settings()

    if settings.use_s3:
        if settings.S3_ACCESS_KEY is None:
            raise RuntimeError(
                "S3_ACCESS_KEY не настроен."
            )

        if settings.S3_SECRET_KEY is None:
            raise RuntimeError(
                "S3_SECRET_KEY не настроен."
            )

        return S3Storage(
            endpoint_url=(
                settings.s3_endpoint_url
            ),
            public_endpoint_url=(
                settings.s3_public_endpoint_url
            ),
            access_key=(
                settings.S3_ACCESS_KEY
            ),
            secret_key=(
                settings.S3_SECRET_KEY
            ),
            region=settings.S3_REGION,
            bucket=settings.s3_bucket,
            verify_ssl=settings.S3_VERIFY_SSL,
        )

    return LocalStorage(
        root=settings.STORAGE_LOCAL_ROOT,
        public_base_url=(
            settings.storage_public_base_url
        ),
    )
