# app/core/storage/school_storage.py (Единый SchoolStorageService)

from __future__ import annotations

from datetime import date

from app.core.storage.base import BaseStorage
from app.core.storage.key_builder import SchoolObjectKeyBuilder

from app.core.storage.schemas import SchoolStorageContext, StoredFile


class SchoolStorageService:
    MAX_FILE_SIZE = 20 * 1024 * 1024

    def __init__(
        self,
        storage: BaseStorage,
    ) -> None:
        self._storage = storage

    async def save_task_report(
        self,
        *,
        context: SchoolStorageContext,
        document_id: int,
        report_code: str,
        content: bytes,
        original_file_name: str,
        content_type: str,
    ) -> StoredFile:
        self._validate_content(content)

        object_key, stored_file_name = (
            SchoolObjectKeyBuilder
            .build_task_report_key(
                context=context,
                document_id=document_id,
                report_code=report_code,
                original_file_name=(
                    original_file_name
                ),
            )
        )

        e_tag = await self._storage.save(
            content=content,
            object_key=object_key,
            content_type=content_type,
            metadata=self._build_metadata(
                original_file_name=(
                    original_file_name
                ),
                document_type="task-report",
            ),
        )

        return self._build_result(
            object_key=object_key,
            stored_file_name=stored_file_name,
            original_file_name=original_file_name,
            content_type=content_type,
            content=content,
            e_tag=e_tag,
        )

    async def save_final_document(
        self,
        *,
        context: SchoolStorageContext,
        document_id: int,
        content: bytes,
        original_file_name: str,
        content_type: str,
    ) -> StoredFile:
        self._validate_content(content)

        object_key, stored_file_name = (
            SchoolObjectKeyBuilder
            .build_final_document_key(
                context=context,
                document_id=document_id,
                original_file_name=(
                    original_file_name
                ),
            )
        )

        e_tag = await self._storage.save(
            content=content,
            object_key=object_key,
            content_type=content_type,
            metadata=self._build_metadata(
                original_file_name=(
                    original_file_name
                ),
                document_type="final-document",
            ),
        )

        return self._build_result(
            object_key=object_key,
            stored_file_name=stored_file_name,
            original_file_name=original_file_name,
            content_type=content_type,
            content=content,
            e_tag=e_tag,
        )

    async def save_review_protocol(
        self,
        *,
        context: SchoolStorageContext,
        review_place: str,
        protocol_number: str,
        protocol_date: date,
        content: bytes,
        original_file_name: str,
        content_type: str,
    ) -> StoredFile:
        self._validate_content(content)

        object_key, stored_file_name = (
            SchoolObjectKeyBuilder
            .build_review_protocol_key(
                context=context,
                review_place=review_place,
                protocol_number=protocol_number,
                protocol_date=protocol_date,
                original_file_name=(
                    original_file_name
                ),
            )
        )

        e_tag = await self._storage.save(
            content=content,
            object_key=object_key,
            content_type=content_type,
            metadata=self._build_metadata(
                original_file_name=(
                    original_file_name
                ),
                document_type="review-protocol",
            ),
        )

        return self._build_result(
            object_key=object_key,
            stored_file_name=stored_file_name,
            original_file_name=original_file_name,
            content_type=content_type,
            content=content,
            e_tag=e_tag,
        )

    async def delete(
        self,
        *,
        object_key: str,
    ) -> None:
        await self._storage.delete(
            object_key=object_key
        )

    async def get_download_url(
        self,
        *,
        object_key: str,
        expires_in: int = 300,
    ) -> str:
        return await self._storage.get_download_url(
            object_key=object_key,
            expires_in=expires_in,
        )

    def _validate_content(
        self,
        content: bytes,
    ) -> None:
        if not content:
            raise ValueError(
                "Файл пуст."
            )

        if len(content) > self.MAX_FILE_SIZE:
            raise ValueError(
                "Размер файла превышает 20 МБ."
            )

    @staticmethod
    def _build_metadata(
        *,
        original_file_name: str,
        document_type: str,
    ) -> dict[str, str]:
        return {
            "original-name": (
                original_file_name
                .encode(
                    "ascii",
                    errors="ignore",
                )
                .decode("ascii")[:200]
                or "-"
            ),
            "document-type": document_type,
        }

    @staticmethod
    def _build_result(
        *,
        object_key: str,
        stored_file_name: str,
        original_file_name: str,
        content_type: str,
        content: bytes,
        e_tag: str | None,
    ) -> StoredFile:
        return StoredFile(
            object_key=object_key,
            stored_file_name=stored_file_name,
            original_file_name=(
                original_file_name
            ),
            content_type=content_type,
            file_size=len(content),
            e_tag=e_tag,
        )
