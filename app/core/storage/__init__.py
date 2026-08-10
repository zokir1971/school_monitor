# app/core/storage/__init__.py

from app.core.storage.base import BaseStorage
from app.core.storage.factory import get_storage
from app.core.storage.schemas import (
    SchoolStorageContext,
    StoredFile,
)

__all__ = [
    "BaseStorage",
    "SchoolStorageContext",
    "StoredFile",
    "get_storage",
]
