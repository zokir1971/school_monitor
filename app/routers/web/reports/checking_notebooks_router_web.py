# routers/checking_notebooks_router.py

from pathlib import Path

import jwt
from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.reports.repositories.checking_notebooks_repo import CheckingNotebooksRepo
from app.modules.reports.repositories.template_repo import TemplateReportRepo
from app.modules.reports.services.checking_notebooks_service import CheckingNotebooksService
from app.modules.reports.utils.report_signature import ReportSignatureService
from app.modules.users.deps import require_roles
from app.modules.users.models import User, UserRole
from app.routers.web.web_common import templates

router = APIRouter(prefix="/staff/reports", tags=["Checking Notebooks Web"])


@router.get(
    "/{month_item_id}/templates/{selected_report_id}/checking-notebooks/fill",
    name="checking_notebooks_fill_page",
    response_class=HTMLResponse,
)
async def checking_notebooks_fill_page(
        request: Request,
        month_item_id: int,
        selected_report_id: int,
        template_id: int | None = None,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    try:
        page_data = await CheckingNotebooksService.get_checking_notebooks_fill_page_data(
            db,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            template_id=template_id,
            user=user,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return templates.TemplateResponse(
        "staff/reports/user_templates/checking_notebooks_fill.html",
        {
            "request": request,
            "user": user,

            "month_item_id": page_data.month_item_id,
            "selected_report_id": page_data.selected_report_id,
            "task_execution_document_id": page_data.task_execution_document_id,

            "template": page_data.template,
            "schema": page_data.schema,
            "criteria": page_data.criteria,
            "score_scale": page_data.score_scale,

            "scores": page_data.scores,
            "saved_info": page_data.saved_info,

            "rows": page_data.rows,
            "total_score": page_data.total_score,
            "max_score": page_data.max_score,
            "percent": page_data.percent,
            "level": page_data.level,

            "report": page_data.report,
            "document": page_data.document,

            "readonly": (
                page_data.report.submitted_at is not None
                if page_data.report else False
            ),

            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post(
    "/{month_item_id}/templates/{selected_report_id}/checking-notebooks/fill",
    name="staff_user_checking_notebooks_fill_submit",
)
async def staff_user_checking_notebooks_fill_submit(
        request: Request,
        month_item_id: int,
        selected_report_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    form = await request.form()

    document = await TemplateReportRepo.get_template_document(
        db,
        selected_report_id=selected_report_id,
        user_id=user.id,
    )

    if not document:
        raise HTTPException(status_code=404, detail="Документ отчета не найден")

    try:
        await CheckingNotebooksService.save_or_complete(
            db,
            request=request,
            form=form,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            task_execution_document_id=document.id,
            _user=user,
            templates=templates,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return RedirectResponse(
        request.url_for(
            "checking_notebooks_fill_page",
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
        ),
        status_code=303,
    )


@router.post(
    "/{month_item_id}/documents/{document_id}/checking-notebooks/save",
    name="checking_notebooks_save_post",
)
async def checking_notebooks_save_post(
        request: Request,
        month_item_id: int,
        document_id: int,
        selected_report_id: int = Query(...),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    form = await request.form()

    try:
        report = await CheckingNotebooksService.save_or_complete(
            db,
            request=request,
            form=form,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            task_execution_document_id=document_id,
            _user=user,
            templates=templates,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if form.get("action") == "complete":
        return RedirectResponse(
            request.url_for(
                "checking_notebooks_pdf_view",
                report_id=report.id,
            ),
            status_code=303,
        )

    return RedirectResponse(
        request.url_for(
            "checking_notebooks_fill_page",
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
        ),
        status_code=303,
    )


@router.get(
    "/checking-notebooks/{report_id}/pdf/view",
    name="checking_notebooks_pdf_view",
)
async def checking_notebooks_pdf_view(
        report_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    report = await CheckingNotebooksRepo.get_by_id(db, report_id)

    if not report:
        raise HTTPException(status_code=404, detail="Отчет не найден")

    document = await CheckingNotebooksRepo.get_document_by_id(
        db,
        report.task_execution_document_id,
    )

    if not document:
        raise HTTPException(status_code=404, detail="Документ отчета не найден")

    allowed_document = await TemplateReportRepo.get_template_document(
        db,
        selected_report_id=document.selected_report_id,
        user_id=user.id,
    )

    if not allowed_document:
        raise HTTPException(status_code=403, detail="Нет доступа к отчету")

    if allowed_document.id != document.id:
        raise HTTPException(status_code=403, detail="Нет доступа к отчету")

    pdf_file = report.pdf_signed_file

    if not pdf_file:
        raise HTTPException(status_code=404, detail="PDF не найден")

    pdf_path = Path(str(pdf_file)).resolve()

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF-файл отсутствует на сервере")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"checking_notebooks_{report.id}.pdf",
        headers={
            "Content-Disposition": f'inline; filename="checking_notebooks_{report.id}.pdf"'
        },
    )


@router.get(
    "/checking-notebooks/{report_id}/pdf/download",
    name="checking_notebooks_pdf_download",
)
async def checking_notebooks_pdf_download(
        report_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    report = await CheckingNotebooksRepo.get_by_id(db, report_id)

    if not report:
        raise HTTPException(status_code=404, detail="Отчет не найден")

    document = await CheckingNotebooksRepo.get_document_by_id(
        db,
        report.task_execution_document_id,
    )

    if not document:
        raise HTTPException(status_code=404, detail="Документ отчета не найден")

    allowed_document = await TemplateReportRepo.get_template_document(
        db,
        selected_report_id=document.selected_report_id,
        user_id=user.id,
    )

    if not allowed_document or allowed_document.id != document.id:
        raise HTTPException(status_code=403, detail="Нет доступа к отчету")

    pdf_file = report.pdf_signed_file

    if not pdf_file:
        raise HTTPException(status_code=404, detail="PDF не найден")

    pdf_path = Path(str(pdf_file)).resolve()

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF-файл отсутствует на сервере")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"checking_notebooks_{report.id}.pdf",
        headers={
            "Content-Disposition": f'attachment; filename="checking_notebooks_{report.id}.pdf"'
        },
    )


@router.get(
    "/checking-notebooks/verify",
    name="checking_notebooks_verify_page",
    response_class=HTMLResponse,
)
async def checking_notebooks_verify_page(
        request: Request,
        token: str,
        db: AsyncSession = Depends(get_db),
):
    payload = None

    try:
        payload = ReportSignatureService.decode_token(token)

        if payload.get("report_type") != "checking_notebooks":
            raise jwt.InvalidTokenError("Неверный тип документа")

    except jwt.ExpiredSignatureError:
        valid = False
        message = "Срок действия подписи истек"
        report = None

    except jwt.InvalidTokenError:
        valid = False
        message = "Неверная подпись документа"
        report = None
    else:
        report_id = payload.get("report_id")

        if not report_id:
            valid = False
            message = "В подписи отсутствует ID отчета"
            report = None
        else:
            report = await CheckingNotebooksRepo.get_by_id(db, int(report_id))

            if not report:
                valid = False
                message = "Документ не найден"
            elif report.submitted_at is None:
                valid = False
                message = "Документ найден, но еще не подписан"
            else:
                valid = True
                message = "Документ подлинный"

    return templates.TemplateResponse(
        "staff/reports/checking_notebooks_verify.html",
        {
            "request": request,
            "valid": valid,
            "message": message,
            "report": report,
            "payload": payload,
        },
    )
