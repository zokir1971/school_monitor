# app/routers/web/reports/report_verify_router.py

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.reports.repositories.report_verify_repo import ReportVerifyRepo
from app.modules.reports.services.report_verify_service import (
    ReportVerifyService,
)
from app.routers.web.web_common import templates

router = APIRouter(prefix="/staff/reports", tags=["Report Verify Web"])


@router.get(
    "/reports/verify/{code}",
    name="report_verify_by_code_page",
    response_class=HTMLResponse,
)
async def report_verify_by_code_page(
        request: Request,
        code: str,
        db: AsyncSession = Depends(get_db),
):
    signature = await ReportVerifyRepo.get_signature_by_code(
        db,
        code=code,
    )

    if not signature:
        result = {
            "valid": False,
            "message": "QR-код жарамсыз",
            "error": "QR-код недействителен",
        }
    else:
        result = await ReportVerifyService.verify(
            db,
            token=signature.token,
        )

    return templates.TemplateResponse(
        "staff/reports/verify_report.html",
        {
            "request": request,
            "result": result,
            **result,
        },
        status_code=200 if result.get("valid") else 400,
    )
