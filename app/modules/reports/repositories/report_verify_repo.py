# app/modules/reports/repositories/report_verify_repo.py

import secrets

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reports.models_template_reports import (
    LessonObservationReport,
    CheckingNotebooksReport,
)
from app.modules.reports.models_report_signature_token import ReportSignatureToken


class ReportVerifyRepo:

    @staticmethod
    async def get_lesson_observation_by_id(
            db: AsyncSession,
            report_id: int,
    ) -> LessonObservationReport | None:
        result = await db.execute(
            select(LessonObservationReport)
            .where(LessonObservationReport.id == report_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_checking_notebooks_by_id(
            db: AsyncSession,
            report_id: int,
    ) -> CheckingNotebooksReport | None:
        result = await db.execute(
            select(CheckingNotebooksReport)
            .where(CheckingNotebooksReport.id == report_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_signature_token(
            db: AsyncSession,
            *,
            token: str,
            report_type: str,
            report_id: int | None,
            document_id: int | None,
    ) -> ReportSignatureToken:
        code = secrets.token_urlsafe(8)

        item = ReportSignatureToken(
            code=code,
            token=token,
            report_type=report_type,
            report_id=report_id,
            document_id=document_id,
            is_active=True,
        )

        db.add(item)
        await db.flush()

        return item

    @staticmethod
    async def get_signature_by_code(
            db: AsyncSession,
            *,
            code: str,
    ) -> ReportSignatureToken | None:
        result = await db.execute(
            select(ReportSignatureToken)
            .where(
                ReportSignatureToken.code == code,
                ReportSignatureToken.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def deactivate_old_signatures(
            db: AsyncSession,
            *,
            report_type: str,
            report_id: int,
            document_id: int | None = None,
    ) -> None:
        stmt = (
            update(ReportSignatureToken)
            .where(
                ReportSignatureToken.report_type == report_type,
                ReportSignatureToken.report_id == report_id,
                ReportSignatureToken.is_active.is_(True),
            )
            .values(is_active=False)
        )

        if document_id is not None:
            stmt = stmt.where(
                ReportSignatureToken.document_id == document_id
            )

        await db.execute(stmt)
