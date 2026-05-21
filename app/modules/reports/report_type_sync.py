# app/modules/reports/report_type_sync.py (Сервис синхронизации типов отчетов)

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reports.enums import ReportType
from app.modules.reports.models_documents import ReportTypeModel

logger = logging.getLogger(__name__)


class ReportTypeSyncService:
    @staticmethod
    def _build_enum_items() -> list[dict]:
        items: list[dict] = []

        default_sort_order = {
            ReportType.LESSON_OBSERVATION.value: 10,
            ReportType.KNOWLEDGE_QUALITY_TABLE.value: 20,
            ReportType.CHECKING_NOTEBOOKS_TABLE.value: 30,
            ReportType.READING_SPEED_TABLE.value: 40,
            ReportType.DOCUMENT_ANALYSIS.value: 50,
            ReportType.ANALYTICAL_REFERENCE.value: 60,
            ReportType.CLASS_SUMMARY.value: 70,
            ReportType.TEACHER_ANALYSIS.value: 80,
        }

        default_name_ru = {
            ReportType.LESSON_OBSERVATION.value: "Лист наблюдения урока",
            ReportType.KNOWLEDGE_QUALITY_TABLE.value: "Таблица качества знаний",
            ReportType.CHECKING_NOTEBOOKS_TABLE.value: "Таблица проверки тетрадей",
            ReportType.READING_SPEED_TABLE.value: "Таблица скорости чтения",
            ReportType.DOCUMENT_ANALYSIS.value: "Анализ документов",
            ReportType.ANALYTICAL_REFERENCE.value: "Аналитическая справка",
            ReportType.CLASS_SUMMARY.value: "Сводная таблица анализа",
            ReportType.TEACHER_ANALYSIS.value: "Анализ работы учителя",
        }

        for item in ReportType:
            items.append(
                {
                    "code": item.value,
                    "name_kz": item.label_kz,
                    "name_ru": default_name_ru.get(item.value),
                    "sort_order": default_sort_order.get(item.value, 100),
                    "is_active": True,
                }
            )

        return items

    @classmethod
    async def sync_report_types(
        cls,
        db: AsyncSession,
        *,
        deactivate_missing: bool = False,
        commit: bool = True,
    ) -> dict[str, int]:
        enum_items = cls._build_enum_items()

        rows = await db.execute(
            select(ReportTypeModel)
        )
        existing_rows = rows.scalars().all()
        existing_by_code = {row.code: row for row in existing_rows}

        created = 0
        updated = 0
        unchanged = 0

        enum_codes = set()

        for item in enum_items:
            code = item["code"]
            enum_codes.add(code)

            existing = existing_by_code.get(code)
            if not existing:
                db.add(
                    ReportTypeModel(
                        code=code,
                        name_kz=item["name_kz"],
                        name_ru=item["name_ru"],
                        is_active=item["is_active"],
                        sort_order=item["sort_order"],
                    )
                )
                created += 1
                continue

            changed = False

            if existing.name_kz != item["name_kz"]:
                existing.name_kz = item["name_kz"]
                changed = True

            if existing.name_ru != item["name_ru"]:
                existing.name_ru = item["name_ru"]
                changed = True

            if existing.sort_order != item["sort_order"]:
                existing.sort_order = item["sort_order"]
                changed = True

            if existing.is_active != item["is_active"]:
                existing.is_active = item["is_active"]
                changed = True

            if changed:
                updated += 1
            else:
                unchanged += 1

        if deactivate_missing:
            for row in existing_rows:
                if row.code not in enum_codes and row.is_active:
                    row.is_active = False
                    updated += 1

        await db.flush()

        if commit:
            await db.commit()

        logger.info(
            "report_types sync finished: created=%s, updated=%s, unchanged=%s",
            created,
            updated,
            unchanged,
        )

        return {
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
        }
