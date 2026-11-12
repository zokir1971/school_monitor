# app/modules/reports/repositories/report_verify_repo.py

import secrets

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.reports.repositories.lesson_observation_repo import LessonObservationRepo
from app.modules.reports.repositories.checking_notebooks_repo import CheckingNotebooksRepo

from app.modules.reports.models_template_reports import (
    LessonObservationReport,
    CheckingNotebooksReport,
)
from app.modules.reports.models_report_signature_token import ReportSignatureToken


class ReportVerifyRepo:

    get_lesson_observation_by_id = staticmethod(LessonObservationRepo.get_by_id)

    get_checking_notebooks_by_id = staticmethod(CheckingNotebooksRepo.get_by_id)

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


    @staticmethod
    async def get_active_signature_for_document(db, *, report_type, document_id):
        result=await db.execute(select(ReportSignatureToken).where(
            ReportSignatureToken.report_type==report_type,
            ReportSignatureToken.report_id==document_id,
            ReportSignatureToken.document_id==document_id,
            ReportSignatureToken.is_active.is_(True))
            .order_by(ReportSignatureToken.id.desc()).limit(1))
        return result.scalar_one_or_none()
