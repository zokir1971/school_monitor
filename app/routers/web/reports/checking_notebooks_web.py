# app/routers/web/reperts/checking_notebooks_router.py

from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage.factory import get_storage
from app.db.session import get_db
from app.modules.reports.repositories.checking_notebooks_repo import CheckingNotebooksRepo
from app.modules.reports.services.checking_notebooks_service import CheckingNotebooksService
from app.modules.reports.services.execution_document_service import ExecutionDocumentService
from app.modules.reports.utils.report_signature import ReportSignatureService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.web_common import templates
from app.routers.web.helpers.render import render

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
        template_id: int | None = Query(default=None),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    """
    Страница заполнения проверки тетрадей.

    GET является read-only:
    - не создает TaskExecutionDocument;
    - не сохраняет шаблон;
    - не создает черновик.

    template_id:
    - None -> системный preview;
    - int  -> пользовательский preview.

    Если документ уже существует, сервис использует schema_json
    документа как snapshot и template_id больше не является
    источником истины.
    """

    try:
        page_data = (
            await CheckingNotebooksService
            .get_checking_notebooks_fill_page_data(
                db,
                month_item_id=month_item_id,
                selected_report_id=selected_report_id,
                template_id=template_id,
                user=user,
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return render(
        templates,
        request,
        "staff/reports/user_templates/checking_notebooks_fill.html",
        {
            "user": user,

            "month_item_id": page_data.month_item_id,
            "selected_report_id": page_data.selected_report_id,
            "task_execution_document_id": (
                page_data.task_execution_document_id
            ),

            "template_id": template_id,

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
                if page_data.report
                else False
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
        template_id: int | None = Query(default=None),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    """
    Сохранение/подписание проверки тетрадей.

    TaskExecutionDocument при первом сохранении создается внутри
    CheckingNotebooksService.save_or_complete().
    """

    form = await request.form()

    try:
        await CheckingNotebooksService.save_or_complete(
            db,
            request=request,
            form=form,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            user=user,
            templates=templates,
            template_id=template_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    action = str(
        form.get("action") or "save"
    ).strip()

    if action == "complete":
        templates_page_url = str(
            request.url_for(
                "staff_report_templates_page",
                month_item_id=month_item_id,
            )
        )

        month = request.query_params.get("month")

        query: dict[str, str] = {
            "success": "Отчет сохранен и подписан.",
        }

        if month:
            query["month"] = month

        return RedirectResponse(
            url=f"{templates_page_url}?{urlencode(query)}",
            status_code=303,
        )

    fill_page_url = str(
        request.url_for(
            "checking_notebooks_fill_page",
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
        )
    )

    query: dict[str, str | int] = {
        "success": "Черновик сохранен.",
    }

    if template_id is not None:
        query["template_id"] = template_id

    month = request.query_params.get("month")

    if month:
        query["month"] = month

    return RedirectResponse(
        url=f"{fill_page_url}?{urlencode(query)}",
        status_code=303,
    )


@router.get(
    "/checking-notebooks/{report_id}/pdf/view",
    name="checking_notebooks_pdf_view",
)
async def checking_notebooks_pdf_view(
        report_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    report = await CheckingNotebooksRepo.get_by_id(db, report_id)

    if not report:
        raise HTTPException(
            status_code=404,
            detail="Отчет не найден",
        )

    document = await ExecutionDocumentService.get_document_for_access(
        db,
        document_id=report.task_execution_document_id,
        user_id=user.id,
        user_role=user.role,
    )

    if not document:
        raise HTTPException(
            status_code=403,
            detail="Документ не найден или нет доступа к отчету",
        )

    pdf_file = report.pdf_signed_file

    if not pdf_file:
        raise HTTPException(
            status_code=404,
            detail="PDF не найден",
        )

    storage = get_storage()

    if not await storage.exists(
        object_key=str(pdf_file),
    ):
        raise HTTPException(
            status_code=404,
            detail="PDF-файл не найден в хранилище",
        )

    download_url = await storage.get_download_url(
        object_key=str(pdf_file),
        expires_in=300,
    )

    return RedirectResponse(
        url=download_url,
        status_code=302,
    )


@router.get(
    "/checking-notebooks/{report_id}/pdf/download",
    name="checking_notebooks_pdf_download",
)
async def checking_notebooks_pdf_download(
        report_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    report = await CheckingNotebooksRepo.get_by_id(db, report_id)

    if not report:
        raise HTTPException(
            status_code=404,
            detail="Отчет не найден",
        )

    document = await ExecutionDocumentService.get_document_for_access(
        db,
        document_id=report.task_execution_document_id,
        user_id=user.id,
        user_role=user.role,
    )

    if not document:
        raise HTTPException(
            status_code=403,
            detail="Документ не найден или нет доступа к отчету",
        )

    pdf_file = report.pdf_signed_file

    if not pdf_file:
        raise HTTPException(
            status_code=404,
            detail="PDF не найден",
        )

    storage = get_storage()

    if not await storage.exists(
        object_key=str(pdf_file),
    ):
        raise HTTPException(
            status_code=404,
            detail="PDF-файл не найден в хранилище",
        )

    download_url = await storage.get_download_url(
        object_key=str(pdf_file),
        expires_in=300,
    )

    return RedirectResponse(
        url=download_url,
        status_code=302,
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

    return render(
        templates,
        request,
        "staff/reports/checking_notebooks_verify.html",
        {
            "valid": valid,
            "message": message,
            "report": report,
            "payload": payload,
        },
    )
