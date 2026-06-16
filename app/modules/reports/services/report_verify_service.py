# app/modules/reports/services/report_verify_service.py
from dataclasses import asdict
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reports.system_report_dto.report_verify_dto import ReportVerifyViewDTO
from app.modules.reports.utils.report_signature import ReportSignatureService
from app.modules.reports.utils.report_verify_registry import ReportVerifyRegistry


class ReportVerifyService:

    @classmethod
    async def verify(
            cls,
            db: AsyncSession,
            *,
            token: str,
    ) -> dict:

        try:
            payload = ReportSignatureService.decode_token(token)

            report_type = payload.get("type")
            report_id = payload.get("report_id")
            document_id = payload.get("document_id")
            total = payload.get("total")

            if not report_type:
                raise ValueError("Тип отчета не указан")

            handler = ReportVerifyRegistry.get(report_type)

            dto = await handler.build(
                db,
                report_id=report_id,
                document_id=document_id,
                total=total,
            )

            return asdict(dto)

        except Exception as e:

            return asdict(
                ReportVerifyViewDTO(
                    valid=False,
                    error=str(e),
                )
            )
