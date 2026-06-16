# app/routers/web/reports/template_report_web.py
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.planning.enums import PlanItemStatus
from app.modules.reports.enums import ReportType, DocumentType, TaskCompletionMode, TaskDocumentStatus
from app.modules.reports.report_service import ReportService
from app.modules.reports.services.template_service import TemplateReportService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.web_common import templates

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/staff/reports",
    tags=["staff-report-templates"],
)


@router.get(
    "/{month_item_id}/templates",
    name="staff_report_templates_page",
    response_class=HTMLResponse,
)
async def staff_report_templates_page(
        request: Request,
        month_item_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    try:
        page_data = await TemplateReportService.get_templates_page_data(
            db,
            month_item_id=month_item_id,
            user_id=user.id,
        )

    except ValueError as e:

        return templates.TemplateResponse(
            "staff/reports/template_reports.html",
            {
                "request": request,
                "user": user,

                "task": None,
                "reports": [],

                "task_topic": None,
                "task_month": None,

                "month": request.query_params.get("month"),

                "all_reports_signed": False,
                "required_reports_count": 0,
                "signed_reports_count": 0,

                "task_status": None,
                "is_done": False,

                "completion_mode": None,
                "is_simple_final_document": False,
                "is_final_with_system_reports": False,

                "final_documents": [],
                "current_final_document": None,

                "review_reports_text": None,
                "review_place_text": None,

                "has_final_document": False,
                "final_document_status": None,

                "execution": None,
                "completion_modes": TaskCompletionMode,

                "error": str(e),
                "success": None,
                "warning": None,
            },
            status_code=404,
        )

    task = page_data["task"]

    final_documents = page_data.get(
        "final_documents",
        [],
    )

    current_final_document = (
        page_data.get("current_final_document")
        or (
            final_documents[0]
            if final_documents
            else None
        )
    )

    is_done = bool(
        task
        and task.status == PlanItemStatus.DONE
    )

    final_locked = bool(
        current_final_document
        and current_final_document.status == TaskDocumentStatus.SUBMITTED
        and current_final_document.file_path
    )

    completion_mode = page_data.get(
        "completion_mode"
    )

    is_simple_final_document = bool(
        page_data.get(
            "is_simple_final_document",
            False,
        )
    )

    is_final_with_system_reports = bool(
        page_data.get(
            "is_final_with_system_reports",
            False,
        )
    )

    return templates.TemplateResponse(
        "staff/reports/template_reports.html",
        {
            "request": request,
            "user": user,

            "task": task,
            "reports": page_data.get(
                "reports",
                [],
            ),

            "task_topic": page_data.get(
                "task_topic"
            ),

            "task_month": page_data.get(
                "task_month"
            ),

            "month": request.query_params.get(
                "month"
            ),

            "all_reports_signed": page_data.get(
                "all_reports_signed",
                False,
            ),

            "required_reports_count": page_data.get(
                "required_reports_count",
                0,
            ),

            "signed_reports_count": page_data.get(
                "signed_reports_count",
                0,
            ),

            "task_status": (
                task.status
                if task
                else None
            ),

            "is_done": is_done,
            "final_locked": final_locked,

            "completion_mode": completion_mode,

            "is_simple_final_document": (
                is_simple_final_document
            ),

            "is_final_with_system_reports": (
                is_final_with_system_reports
            ),

            "final_documents": final_documents,

            "current_final_document": (
                current_final_document
            ),

            "review_reports_text": page_data.get(
                "review_reports_text"
            ),

            "review_place_text": page_data.get(
                "review_place_text"
            ),

            "has_final_document": page_data.get(
                "has_final_document",
                False,
            ),

            "final_document_status": page_data.get(
                "final_document_status"
            ),

            "execution": page_data.get(
                "execution"
            ),

            "completion_modes": TaskCompletionMode,

            "error": request.query_params.get(
                "error"
            ),

            "success": request.query_params.get(
                "success"
            ),

            "warning": request.query_params.get(
                "warning"
            ),
        },
    )


@router.post(
    "/{month_item_id}/templates/complete",
    name="staff_report_templates_complete_post",
)
async def staff_report_templates_complete_post(
        request: Request,
        month_item_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    form = await request.form()

    base_url = str(
        request.url_for(
            "staff_report_templates_page",
            month_item_id=month_item_id,
        )
    )

    try:
        page_data = await TemplateReportService.get_templates_page_data(
            db,
            month_item_id=month_item_id,
            user_id=user.id,
        )

        if not page_data.get("all_reports_signed"):
            return RedirectResponse(
                url=f"{base_url}?error=Сначала заполните и подпишите все системные отчеты.",
                status_code=303,
            )

        upload_file = form.get("final_document")

        if upload_file is None or not getattr(upload_file, "filename", ""):
            return RedirectResponse(
                url=f"{base_url}?error=Выберите итоговый документ.",
                status_code=303,
            )

        task = page_data["task"]

        if task.status == PlanItemStatus.DONE:
            return RedirectResponse(
                url=f"{base_url}?warning=Задача уже завершена.",
                status_code=303,
            )

        await ReportService.upload_final_document(
            db,
            month_item_id=month_item_id,
            user_id=user.id,
            required_document_id=None,
            upload_file=upload_file,
            document_type=DocumentType.REFERENCE,
        )

        await ReportService.complete_task_execution(
            db,
            month_item_id=month_item_id,
            user_id=user.id,
            completion_mode=TaskCompletionMode.FINAL_WITH_SYSTEM_REPORTS,
        )

        return RedirectResponse(
            url=f"{base_url}?success=Итоговый документ загружен. Задача отправлена на рассмотрение.",
            status_code=303,
        )

    except HTTPException:
        raise

    except (ValueError, TypeError) as e:
        return RedirectResponse(
            url=f"{base_url}?error={str(e)}",
            status_code=303,
        )

    except OSError:
        logger.exception(
            "Ошибка файловой системы при завершении через системные отчеты: month_item_id=%s, user_id=%s",
            month_item_id,
            user.id,
        )
        return RedirectResponse(
            url=f"{base_url}?error=Ошибка при работе с файлом.",
            status_code=303,
        )

    except SQLAlchemyError:
        logger.exception(
            "Ошибка БД при завершении через системные отчеты: month_item_id=%s, user_id=%s",
            month_item_id,
            user.id,
        )
        return RedirectResponse(
            url=f"{base_url}?error=Ошибка при сохранении данных.",
            status_code=303,
        )


@router.get(
    "/{month_item_id}/templates/{selected_report_id}",
    name="staff_report_template_edit_page",
    response_class=HTMLResponse,
)
async def staff_report_template_edit_page(
        request: Request,
        month_item_id: int,
        selected_report_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    """
    Открыть форму конкретного системного отчета.

    Сейчас поддерживаем:
    - lesson_observation

    Позже сюда добавляются остальные шаблоны через report_code.
    """
    try:
        page_data = await TemplateReportService.get_lesson_observation_form_data(
            db,
            selected_report_id=selected_report_id,
            user=user,
        )

    except ValueError as e:
        return templates.TemplateResponse(
            "staff/reports/template_report_edit.html",
            {
                "request": request,
                "user": user,
                "month_item_id": month_item_id,
                "selected_report_id": selected_report_id,
                "selected_report": None,
                "report_type": None,
                "document": None,
                "lesson_report": None,
                "error": str(e),
                "success": None,
            },
            status_code=404,
        )

    return templates.TemplateResponse(
        "staff/reports/template_report_edit.html",
        {
            "request": request,
            "user": user,
            "month_item_id": month_item_id,
            "selected_report_id": selected_report_id,

            "selected_report": page_data["selected_report"],
            "report_type": page_data["report_type"],
            "document": page_data["document"],
            "lesson_report": page_data["lesson_report"],

            "report_code": ReportType.LESSON_OBSERVATION.value,

            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post(
    "/{month_item_id}/templates/{selected_report_id}",
    name="staff_report_template_save",
)
async def staff_report_template_save(
        request: Request,
        month_item_id: int,
        selected_report_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    """
    Сохранить данные системного шаблона.

    Сейчас сохраняет:
    - lesson_observation

    Позже можно сделать dispatcher по report_code.
    """
    base_url = str(
        request.url_for(
            "staff_report_template_edit_page",
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
        )
    )

    try:
        form = await request.form()

        await TemplateReportService.save_lesson_observation_report(
            db,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            user=user,
            form_data=dict(form),
        )

        return RedirectResponse(
            url=f"{base_url}?success=Отчет успешно сохранен.",
            status_code=303,
        )

    except ValueError as e:
        return RedirectResponse(
            url=f"{base_url}?error={str(e)}",
            status_code=303,
        )

    except SQLAlchemyError:
        logger.exception(
            "Ошибка БД при сохранении шаблона: month_item_id=%s, selected_report_id=%s, user_id=%s",
            month_item_id,
            selected_report_id,
            user.id,
        )
        return RedirectResponse(
            url=f"{base_url}?error=Ошибка при сохранении данных.",
            status_code=303,
        )
