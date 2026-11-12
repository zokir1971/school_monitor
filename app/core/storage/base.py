# app/core/storage/base.py (универсальный интерфейс FileStorage (готов к S3/MinIO))

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseStorage(ABC):
    """
    Низкоуровневый интерфейс файлового хранилища.

    Backend не формирует структуру каталогов и имена.
    Он получает готовый object_key.
    """

    @abstractmethod
    async def save(
        self,
        *,
        content: bytes,
        object_key: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str | None:
        """
        Сохраняет объект.

        Возвращает ETag, если backend его предоставляет.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(
        self,
        *,
        object_key: str,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def exists(
        self,
        *,
        object_key: str,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_download_url(
        self,
        *,
        object_key: str,
        expires_in: int = 300,
    ) -> str:
        raise NotImplementedError

    async def read(self, *, object_key: str, max_bytes: int = 8_000_000) -> bytes:
        raise NotImplementedError('Storage does not support bounded reads')
