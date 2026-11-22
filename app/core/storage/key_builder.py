# app/core/storage/key_builder.py (Построитель структуры хранилища)

from __future__ import annotations

import re
from uuid import uuid4
from datetime import date
from pathlib import Path

from app.core.storage.enums import StorageCategory
from app.core.storage.schemas import SchoolStorageContext


class SchoolObjectKeyBuilder:
    ROOT_PREFIX = "schools"

    @classmethod
    def build_correction_key(cls, *, context, original_file_name):
        cls._validate_context(context, require_school_plan=True, require_month_item=False)
        name = uuid4().hex + cls.get_extension(original_file_name)
        return f"{cls._school_prefix(context)}/school-plan-{context.school_plan_id}/corrections/{name}", name

    @classmethod
    def build_task_report_key(
        cls,
        *,
        context: SchoolStorageContext,
        document_id: int,
        report_code: str,
        original_file_name: str,
    ) -> tuple[str, str]:
        cls._validate_context(
            context,
            require_school_plan=True,
            require_month_item=True,
        )

        extension = cls.get_extension(original_file_name)

        safe_report_code = cls.sanitize(
            report_code
        )

        generated_pdf = re.fullmatch(
            r"(class_summary|knowledge_quality_table|reading_speed_table|document_analysis|teacher_analysis|analytical_reference)_pdf_([0-9a-f]{32})",
            safe_report_code,
        ) if extension == ".pdf" else None

        if generated_pdf:
            # The caller's full UUID already gives each PDF revision a unique key.
            # Keep it once in the filename, under the stable report-type directory.
            safe_report_code, revision_id = generated_pdf.groups()
            stored_file_name = f"document-{document_id}_{revision_id}{extension}"
        else:
            stored_file_name = (
                f"{safe_report_code}_"
                f"document-{document_id}_{uuid4().hex}"
                f"{extension}"
            )

        object_key = (
            f"{cls._school_prefix(context)}/"
            f"school-plan-{context.school_plan_id}/"
            f"{StorageCategory.TASK_REPORT.value}/"
            f"month-item-{context.month_item_id}/"
            f"{safe_report_code}/"
            f"{stored_file_name}"
        )

        return object_key, stored_file_name

    @classmethod
    def build_final_document_key(
        cls,
        *,
        context: SchoolStorageContext,
        document_id: int,
        original_file_name: str,
    ) -> tuple[str, str]:
        cls._validate_context(
            context,
            require_school_plan=True,
            require_month_item=True,
        )

        extension = cls.get_extension(
            original_file_name
        )

        stored_file_name = (
            f"final_document_"
            f"month-item-{context.month_item_id}_"
            f"document-{document_id}_{uuid4().hex}"
            f"{extension}"
        )

        object_key = (
            f"{cls._school_prefix(context)}/"
            f"school-plan-{context.school_plan_id}/"
            f"{StorageCategory.FINAL_DOCUMENT.value}/"
            f"month-item-{context.month_item_id}/"
            f"{stored_file_name}"
        )

        return object_key, stored_file_name

    @classmethod
    def build_review_protocol_key(
        cls,
        *,
        context: SchoolStorageContext,
        review_place: str,
        protocol_number: str,
        protocol_date: date,
        original_file_name: str,
    ) -> tuple[str, str]:
        cls._validate_context(
            context,
            require_school_plan=True,
            require_month_item=False,
        )

        extension = cls.get_extension(
            original_file_name
        )

        safe_review_place = cls.sanitize(
            review_place
        )

        safe_protocol_number = cls.sanitize(
            protocol_number
        )

        stored_file_name = (
            f"{safe_review_place}_"
            f"{safe_protocol_number}_"
            f"{protocol_date.isoformat()}_{uuid4().hex}"
            f"{extension}"
        )

        object_key = (
            f"{cls._school_prefix(context)}/"
            f"school-plan-{context.school_plan_id}/"
            f"{StorageCategory.REVIEW_PROTOCOL.value}/"
            f"{protocol_date.year}/"
            f"{safe_review_place}/"
            f"{stored_file_name}"
        )

        return object_key, stored_file_name

    @classmethod
    def _school_prefix(
        cls,
        context: SchoolStorageContext,
    ) -> str:
        academic_year = cls.sanitize(
            context.academic_year
        )

        return (
            f"{cls.ROOT_PREFIX}/"
            f"region-{context.region_id}/"
            f"district-{context.district_id}/"
            f"school-{context.school_id}/"
            f"academic-year-{academic_year}"
        )

    @staticmethod
    def get_extension(
        original_file_name: str,
    ) -> str:
        extension = (
            Path(original_file_name)
            .suffix
            .lower()
        )

        if not extension:
            raise ValueError(
                "Не удалось определить расширение файла."
            )

        return extension

    @staticmethod
    def sanitize(
        value: str,
    ) -> str:
        normalized = (
            value or ""
        ).strip().lower()

        normalized = re.sub(
            r"[^a-zа-яёәіңғүұқөһ0-9_-]+",
            "_",
            normalized,
            flags=re.IGNORECASE,
        )

        normalized = re.sub(
            r"_+",
            "_",
            normalized,
        )

        return normalized.strip("_") or "unknown"

    @staticmethod
    def _validate_context(
        context: SchoolStorageContext,
        *,
        require_school_plan: bool,
        require_month_item: bool,
    ) -> None:
        if context.region_id <= 0:
            raise ValueError(
                "Некорректный ID региона."
            )

        if context.district_id <= 0:
            raise ValueError(
                "Некорректный ID района."
            )

        if context.school_id <= 0:
            raise ValueError(
                "Некорректный ID школы."
            )

        if not context.academic_year:
            raise ValueError(
                "Учебный год не указан."
            )

        if (
            require_school_plan
            and not context.school_plan_id
        ):
            raise ValueError(
                "Годовой план школы не указан."
            )

        if (
            require_month_item
            and not context.month_item_id
        ):
            raise ValueError(
                "Задача месячного плана не указана."
            )
