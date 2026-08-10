# app/routers/web/reports/task_reports_web.py
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.db.session import get_db
from app.modules.planning.enums import PlanItemStatus
from app.modules.reports.enums import DocumentType, TaskCompletionMode, TaskDocumentStatus
from app.modules.reports.services.execution_service import ExecutionService
from app.modules.reports.services.execution_document_service import ExecutionDocumentService
from app.modules.reports.services.task_reports_service import TaskReportsService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.web_common import templates
from app.routers.web.helpers.render import render, render_error

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
    """
    Рабочая страница отчетов по задаче.

    Для PRIMARY:
    - мои отчеты;
    - полный контроль всех отчетов;
    - завершение задачи.

    Для соисполнителя:
    - только назначенные ему отчеты.
    """

    month = request.query_params.get(
        "month"
    )

    try:
        page_data = await TaskReportsService.get_page_data(
            db,
            month_item_id=month_item_id,
            user_id=user.id,
        )

    except ValueError as exc:
        return render_error(
            templates,
            request,
            "staff/reports/template_reports.html",
            {
                "user": user,

                "page_data": None,
                "task": None,

                "month_item_id": month_item_id,
                "month": month,

                "task_title": None,
                "task_topic": None,
                "task_month": None,
                "task_period_text": "—",

                "current_staff_member_id": None,
                "is_primary_executor": False,
                "is_co_executor": False,
                "executor_role_label": "—",

                "my_reports": [],
                "all_reports": [],
                "reports": [],

                "completion_mode": None,
                "is_simple_final_document": False,
                "is_final_with_system_reports": False,

                "all_reports_completed": False,
                "all_reports_signed": False,

                "required_reports_count": 0,
                "completed_reports_count": 0,
                "signed_reports_count": 0,

                "task_status": None,
                "is_done": False,
                "final_locked": False,

                "final_documents": [],
                "current_final_document": None,
                "has_final_document": False,
                "final_document_status": None,

                "review_reports_text": None,
                "review_place_text": None,

                "success": None,
                "warning": None,
            },
            error=str(exc),
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # =========================================================
    # TASK STATE
    # =========================================================

    task = page_data.task_title

    task_status = page_data.task_status

    is_done = bool(
        task_status == PlanItemStatus.DONE
    )

    current_final_document = (
        page_data.current_final_document
    )

    final_locked = bool(
        current_final_document
        and current_final_document.status
        == TaskDocumentStatus.SUBMITTED
        and current_final_document.file_path
    )

    # =========================================================
    # TEMPLATE
    # =========================================================

    return render(
        templates,
        request,
        "staff/reports/template_reports.html",
        {
            "user": user,

            "page_data": page_data,

            # ---------------------------------------------
            # Задача
            # ---------------------------------------------

            "task": task,

            "month_item_id": (
                page_data.month_item_id
            ),

            "month": month,

            "task_title": (
                page_data.task_title
            ),

            "task_topic": (
                page_data.task_topic
            ),

            "task_month": (
                page_data.task_month
            ),

            "task_period_text": (
                page_data.period_text
            ),

            # ---------------------------------------------
            # Текущий исполнитель
            # ---------------------------------------------

            "current_staff_member_id": (
                page_data.current_staff_member_id
            ),

            "is_primary_executor": (
                page_data.is_primary_executor
            ),

            "is_co_executor": (
                page_data.is_co_executor
            ),

            "executor_role_label": (
                page_data.executor_role_label
            ),

            # ---------------------------------------------
            # Отчеты
            # ---------------------------------------------

            "my_reports": (
                page_data.my_reports
            ),

            "all_reports": (
                page_data.all_reports
            ),

            # Временно оставляем.
            # После переделки template_reports.html
            # это поле можно будет удалить.
            "reports": (
                page_data.reports
            ),

            # ---------------------------------------------
            # Сценарий завершения
            # ---------------------------------------------

            "completion_mode": (
                page_data.completion_mode
            ),

            "is_simple_final_document": (
                page_data.is_simple_final_document
            ),

            "is_final_with_system_reports": (
                page_data.is_final_with_system_reports
            ),

            # ---------------------------------------------
            # Прогресс
            # ---------------------------------------------

            "required_reports_count": (
                page_data.required_reports_count
            ),

            "completed_reports_count": (
                page_data.completed_reports_count
            ),

            "signed_reports_count": (
                page_data.signed_reports_count
            ),

            "all_reports_completed": (
                page_data.all_reports_completed
            ),

            "all_reports_signed": (
                page_data.all_reports_signed
            ),

            # ---------------------------------------------
            # Задача / завершение
            # ---------------------------------------------

            "task_status": (
                task_status
            ),

            "is_done": (
                is_done
            ),

            "final_locked": (
                final_locked
            ),

            # ---------------------------------------------
            # Итоговые документы
            # ---------------------------------------------

            "final_documents": (
                page_data.final_documents
            ),

            "current_final_document": (
                current_final_document
            ),

            "has_final_document": (
                page_data.has_final_document
            ),

            "final_document_status": (
                page_data.final_document_status
            ),

            # ---------------------------------------------
            # Рассмотрение
            # ---------------------------------------------

            "review_reports_text": (
                page_data.review_reports_text
            ),

            "review_place_text": (
                page_data.review_place_text
            ),

            # ---------------------------------------------
            # Сообщения
            # ---------------------------------------------

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
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    form = await request.form()

    base_url = str(
        request.url_for(
            "staff_report_templates_page",
            month_item_id=month_item_id,
        )
    )

    month = request.query_params.get("month")

    def redirect_url(
            *,
            message_type: str,
            message: str,
    ) -> str:
        separator = "&" if "?" in base_url else "?"

        url = (
            f"{base_url}"
            f"{separator}"
            f"{message_type}={message}"
        )

        if month:
            url += f"&month={month}"

        return url

    try:
        page_data = await TaskReportsService.get_page_data(
            db,
            month_item_id=month_item_id,
            user_id=user.id,
        )

        # =========================================================
        # ACCESS
        # =========================================================

        if not page_data.is_primary_executor:
            return RedirectResponse(
                url=redirect_url(
                    message_type="error",
                    message=(
                        "Завершить задачу может только "
                        "ответственный исполнитель."
                    ),
                ),
                status_code=303,
            )

        # =========================================================
        # REPORT RESOLUTION
        # =========================================================
        #
        # Новая логика:
        #
        # COMPLETED -> закрыт
        # WAIVED    -> закрыт
        # PENDING   -> блокирует завершение
        #
        # all_reports_signed здесь больше НЕ используем.
        # =========================================================

        if not page_data.all_reports_resolved:
            return RedirectResponse(
                url=redirect_url(
                    message_type="error",
                    message=(
                        "Есть незакрытые системные отчеты. "
                        "Завершите, переназначьте или освободите "
                        "их от выполнения."
                    ),
                ),
                status_code=303,
            )

        # =========================================================
        # FINAL DOCUMENT
        # =========================================================

        upload_file = form.get("final_document")

        current_final_document = (
            page_data.current_final_document
        )

        has_uploaded_file = bool(
            upload_file
            and getattr(
                upload_file,
                "filename",
                "",
            )
        )

        has_existing_final_document = bool(
            current_final_document
            and current_final_document.file_path
        )

        if (
            not has_uploaded_file
            and not has_existing_final_document
        ):
            return RedirectResponse(
                url=redirect_url(
                    message_type="error",
                    message=(
                        "Сначала выберите итоговый документ."
                    ),
                ),
                status_code=303,
            )

        # =========================================================
        # TASK STATE
        # =========================================================

        if page_data.task_status == PlanItemStatus.DONE:
            return RedirectResponse(
                url=redirect_url(
                    message_type="warning",
                    message="Задача уже завершена.",
                ),
                status_code=303,
            )

        # =========================================================
        # UPLOAD FINAL DOCUMENT
        # =========================================================

        if has_uploaded_file:
            await ExecutionDocumentService.upload_final_document(
                db,
                month_item_id=month_item_id,
                user_id=user.id,
                required_document_id=None,
                upload_file=upload_file,
                document_type=DocumentType.REFERENCE,
            )

        # =========================================================
        # COMPLETE TASK
        # =========================================================

        await ExecutionService.complete_task_execution(
            db,
            month_item_id=month_item_id,
            user_id=user.id,
            completion_mode=(
                TaskCompletionMode.FINAL_WITH_SYSTEM_REPORTS
            ),
        )

        return RedirectResponse(
            url=redirect_url(
                message_type="success",
                message=(
                    "Итоговый документ сохранен. "
                    "Задача отправлена на рассмотрение."
                ),
            ),
            status_code=303,
        )

    except HTTPException:
        raise

    except (ValueError, TypeError) as exc:
        return RedirectResponse(
            url=redirect_url(
                message_type="error",
                message=str(exc),
            ),
            status_code=303,
        )

    except OSError:
        logger.exception(
            "Ошибка файловой системы при завершении "
            "через системные отчеты: "
            "month_item_id=%s, user_id=%s",
            month_item_id,
            user.id,
        )

        return RedirectResponse(
            url=redirect_url(
                message_type="error",
                message="Ошибка при работе с файлом.",
            ),
            status_code=303,
        )

    except SQLAlchemyError:
        logger.exception(
            "Ошибка БД при завершении "
            "через системные отчеты: "
            "month_item_id=%s, user_id=%s",
            month_item_id,
            user.id,
        )

        return RedirectResponse(
            url=redirect_url(
                message_type="error",
                message="Ошибка при сохранении данных.",
            ),
            status_code=303,
        )
