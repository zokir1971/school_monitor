# app/core/storage/__init__.py

from app.core.config import USE_S3
from app.core.storage.local import LocalStorage
from app.core.storage.s3 import S3Storage


def get_storage():
    if USE_S3:
        return S3Storage()
    return LocalStorage()
