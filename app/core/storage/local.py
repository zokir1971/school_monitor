# app/core/storage/local.py (Локальное хранилище для файлов загрузки)

from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.storage.base import BaseStorage


class LocalStorage(BaseStorage):
    def __init__(
            self,
            *,
            root: Path,
            public_base_url: str = "/storage",
    ) -> None:
        self._root = root.resolve()
        self._public_base_url = (
            public_base_url.rstrip("/")
        )

    async def save(
            self,
            *,
            content: bytes,
            object_key: str,
            content_type: str,
            metadata: dict[str, str] | None = None,
    ) -> str | None:
        file_path = self._resolve_object_path(
            object_key
        )

        await asyncio.to_thread(
            self._write_file,
            file_path,
            content,
        )

        return None

    async def delete(
            self,
            *,
            object_key: str,
    ) -> None:
        file_path = self._resolve_object_path(
            object_key
        )

        await asyncio.to_thread(
            self._delete_file,
            file_path,
        )

    async def exists(
            self,
            *,
            object_key: str,
    ) -> bool:
        file_path = self._resolve_object_path(
            object_key
        )

        return await asyncio.to_thread(
            file_path.is_file
        )

    async def get_download_url(
            self,
            *,
            object_key: str,
            expires_in: int = 300,
    ) -> str:
        normalized_key = self._normalize_key(
            object_key
        )

        return (
            f"{self._public_base_url}/"
            f"{normalized_key}"
        )

    def _resolve_object_path(
            self,
            object_key: str,
    ) -> Path:
        normalized_key = self._normalize_key(
            object_key
        )

        file_path = (
                self._root /
                Path(normalized_key)
        ).resolve()

        try:
            file_path.relative_to(
                self._root
            )
        except ValueError as exc:
            raise ValueError(
                "Недопустимый путь объекта."
            ) from exc

        return file_path

    @staticmethod
    def _normalize_key(
            object_key: str,
    ) -> str:
        normalized_key = (
                object_key or ""
        ).strip().replace("\\", "/").lstrip("/")

        if not normalized_key:
            raise ValueError(
                "Ключ объекта не указан."
            )

        return normalized_key

    @staticmethod
    def _write_file(
            file_path: Path,
            content: bytes,
    ) -> None:
        file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        file_path.write_bytes(content)

    @staticmethod
    def _delete_file(
            file_path: Path,
    ) -> None:
        if file_path.is_file():
            file_path.unlink()

    async def read(self, *, object_key: str, max_bytes: int = 8_000_000) -> bytes:
        path = self._resolve_object_path(object_key)

        def load():
            with path.open('rb') as stream:
                data = stream.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ValueError('Image exceeds export limit')
            return data

        return await asyncio.to_thread(load)
