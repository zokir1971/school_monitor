# app/modules/reports/repositories/report_type_repo.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reports.models_documents import ReportTypeModel


class ReportTypeRepo:
    """
    Repository справочника типов отчетов.
    """

    @staticmethod
    async def get_code_id_map(
        db: AsyncSession,
    ) -> dict[str, int]:
        """
        Вернуть отображение report code -> report type id.
        """
        rows = await db.execute(
            select(ReportTypeModel.id, ReportTypeModel.code)
        )
        return {
            str(code): int(report_type_id)
            for report_type_id, code in rows.all()
            if code
        }


    @staticmethod
    async def get_labels(db: AsyncSession) -> dict:
        rows = (await db.execute(select(ReportTypeModel.code,ReportTypeModel.name_ru,ReportTypeModel.name_kz))).all()
        return {str(row.code):dict(ru=row.name_ru or row.name_kz or row.code,
                                 kk=row.name_kz or row.name_ru or row.code) for row in rows if row.code}
