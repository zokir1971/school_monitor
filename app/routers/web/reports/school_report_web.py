from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse

from app.db.session import get_db
from app.modules.planning.enums import PlanItemStatus
from app.modules.reports.enums import DocumentType
from app.modules.reports.report_repo import ReportRepo
from app.modules.reports.report_services import ReportService, FileStorageService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.web_common import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/staff/reports", tags=["staff-reports"])


@router.get(
    "/{month_item_id}/execute",
    name="staff_report_execute_page",
    response_class=HTMLResponse,
)
async def staff_report_execute_page(
        request: Request,
        month_item_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    try:
        page_data = await ReportService.get_execution_page_data(
            db,
            month_item_id=month_item_id,
            user_id=user.id,
            draft_document_type=DocumentType.REFERENCE,
        )
    except ValueError as e:
        return templates.TemplateResponse(
            "staff/report_execute.html",
            {
                "request": request,
                "user": user,
                "task": None,
                "execution": None,
                "required_documents": [],
                "current_draft": None,
                "current_documents": [],
                "final_documents": [],
                "completion_ready": False,
                "draft_document_type": DocumentType.REFERENCE,
                "error": str(e),
                "success": None,
                "warning": None,
            },
            status_code=404,
        )

    return templates.TemplateResponse(
        "staff/report_execute.html",
        {
            "request": request,
            "user": user,
            "task": page_data["task"],
            "task_topic": page_data["task_topic"],
            "task_goal": page_data["task_goal"],
            "review_place_text": page_data["review_place_text"],
            "execution": page_data["execution"],
            "required_documents": page_data["required_documents"],
            "current_draft": page_data["current_draft"],
            "current_documents": page_data["current_documents"],
            "final_documents": page_data["final_documents"],
            "current_final_document": page_data["final_documents"][0] if page_data["final_documents"] else None,
            "completion_ready": page_data["completion_ready"],
            "is_done": page_data["task"].status == PlanItemStatus.DONE if page_data["task"] else False,
            "draft_document_type": page_data["draft_document_type"],
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
            "warning": request.query_params.get("warning"),
        },
    )


@router.post(
    "/{month_item_id}/upload-final",
    name="staff_report_upload_final",
)
async def staff_report_upload_final(
        month_item_id: int,
        required_document_id: int = Form(...),
        title: str | None = Form(default=None),
        reference_file_note: str | None = Form(default=None),
        review_result: str | None = Form(default=None),
        reference_file: UploadFile = File(...),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    try:
        content = await reference_file.read()
        if not content:
            raise ValueError("Файл пустой")

        stored_file_name, file_path = await FileStorageService.save_task_execution_file(
            file_name=reference_file.filename,
            content=content,
        )

        await ReportService.upload_final_document(
            db,
            month_item_id=month_item_id,
            user_id=user.id,
            required_document_id=required_document_id,
            document_type=DocumentType.REFERENCE,
            title=title,
            original_file_name=reference_file.filename,
            stored_file_name=stored_file_name,
            file_path=file_path,
            mime_type=reference_file.content_type,
            file_size=len(content),
            reference_file_note=reference_file_note,
            review_result=review_result,
            auto_complete_task=True,
        )

        return RedirectResponse(
            url=f"/staff/reports/{month_item_id}/execute?success=Итоговый документ загружен",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except ValueError as e:
        await db.rollback()
        return RedirectResponse(
            url=f"/staff/reports/{month_item_id}/execute?warning={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.exception("ERROR in staff_report_upload_final: %s", e)
        return RedirectResponse(
            url=f"/staff/reports/{month_item_id}/execute?error=Внутренняя ошибка",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.post(
    "/tasks/{month_item_id}/execute/save",
    name="staff_task_execute_save",
)
async def staff_task_execute_save(
        request: Request,
        month_item_id: int,
        month: int | None = Form(default=None),
        selected_task_id: int | None = Form(default=None),
        action: str = Form(...),

        control_scope: str | None = Form(default=None),
        control_form: str | None = Form(default=None),
        control_kind: str | None = Form(default=None),
        report_types: list[str] = Form(default=[]),

        evidence_note: str | None = Form(default=None),
        planned_review_place: str | None = Form(default=None),

        reference_text: str | None = Form(default=None),
        conclusion: str | None = Form(default=None),
        recommendations: str | None = Form(default=None),

        reference_file_note: str | None = Form(default=None),
        reference_file: UploadFile | None = File(default=None),

        review_result: str | None = Form(default=None),

        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    current_user_id = int(user.id)
    redirect_month = month or date.today().month
    redirect_selected_task_id = selected_task_id or month_item_id

    def redirect_to_list(param_name: str, message: str) -> RedirectResponse:
        query = urlencode(
            {
                "month": redirect_month,
                "selected_task_id": redirect_selected_task_id,
                param_name: message,
            }
        )
        return RedirectResponse(
            url=f"/staff/tasks/execute?{query}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    def redirect_to_same_page(param_name: str, message: str) -> RedirectResponse:
        base_url = request.url_for(
            "staff_report_execute_page",
            month_item_id=month_item_id,
        )
        query = urlencode(
            {
                "month": redirect_month,
                "selected_task_id": redirect_selected_task_id,
                param_name: message,
            }
        )
        return RedirectResponse(
            url=f"{base_url}?{query}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        logger.info(
            "staff_task_execute_save started: month_item_id=%s, user_id=%s, action=%s",
            month_item_id,
            current_user_id,
            action,
        )

        task = await ReportService.get_task_for_execution(
            db,
            month_item_id=month_item_id,
            user_id=current_user_id,
        )

        if task.status == PlanItemStatus.DONE and action in {
            "upload_final",
            "done",
            "not_executed",
            "save",
            "export_draft",
        }:
            raise ValueError("Задача уже завершена и отправлена на рассмотрение")

        source_row11 = getattr(task, "source_row11", None)
        if source_row11 is None:
            raise ValueError("У задачи отсутствует source_row11")

        required_documents = list(getattr(source_row11, "required_documents", None) or [])
        if not required_documents:
            raise ValueError("Для задачи не настроены обязательные документы")

        required_document = required_documents[0]
        draft_document_type = DocumentType.REFERENCE

        task_title = (
            getattr(source_row11, "topic", None)
            or getattr(task, "topic", None)
            or f"Задача #{task.id}"
        )
        task_goal = (
            getattr(source_row11, "goal", None)
            or getattr(task, "goal", None)
        )

        review_place = planned_review_place or None
        draft_title = "Справка"
        final_title = reference_file_note or "Подписанная справка"

        if action == "save":
            await ReportService.save_reference_draft(
                db,
                month_item_id=month_item_id,
                user_id=current_user_id,
                required_document_id=required_document.id,
                document_type=draft_document_type,
                report_type_codes=report_types,
                title=draft_title,
                task_title=task_title,
                task_goal=task_goal,
                review_place=review_place,
                control_scope=control_scope,
                control_form=control_form,
                control_kind=control_kind,
                evidence_note=evidence_note,
                planned_review_place=planned_review_place,
                reference_text=reference_text,
                conclusion=conclusion,
                recommendations=recommendations,
                reference_file_note=reference_file_note,
                review_result=review_result,
                notes=evidence_note,
            )
            await db.commit()
            return redirect_to_list("success", "Черновик сохранен")

        if action == "export_draft":
            draft = await ReportService.save_reference_draft(
                db,
                month_item_id=month_item_id,
                user_id=current_user_id,
                required_document_id=required_document.id,
                document_type=draft_document_type,
                report_type_codes=report_types,
                title=draft_title,
                task_title=task_title,
                task_goal=task_goal,
                review_place=review_place,
                control_scope=control_scope,
                control_form=control_form,
                control_kind=control_kind,
                evidence_note=evidence_note,
                planned_review_place=planned_review_place,
                reference_text=reference_text,
                conclusion=conclusion,
                recommendations=recommendations,
                reference_file_note=reference_file_note,
                review_result=review_result,
                notes=evidence_note,
            )
            await db.commit()

            if not draft.content_html:
                raise ValueError("Черновой отчет пустой")

            file_name = f"draft_report_{month_item_id}.html"
            html_content = draft.content_html

            return Response(
                content=html_content,
                media_type="text/html; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{file_name}"'
                },
            )

        if action == "upload_final":
            if reference_file is None or not reference_file.filename:
                raise ValueError("Выберите итоговый файл для загрузки")

            content = await reference_file.read()
            if not content:
                raise ValueError("Файл пустой")

            stored_file_name, file_path = await FileStorageService.save_task_execution_file(
                file_name=reference_file.filename,
                content=content,
            )

            await ReportService.upload_final_document(
                db,
                month_item_id=month_item_id,
                user_id=current_user_id,
                required_document_id=required_document.id,
                document_type=draft_document_type,
                title=final_title,
                original_file_name=reference_file.filename,
                stored_file_name=stored_file_name,
                file_path=file_path,
                mime_type=reference_file.content_type,
                file_size=len(content),
                reference_file_note=reference_file_note,
                review_result=review_result,
                auto_complete_task=False,
            )
            await db.commit()
            return redirect_to_same_page("success", "Итоговый документ загружен")

        if action == "done":
            done = await ReportService.try_mark_task_as_done(
                db,
                month_item_id=month_item_id,
            )
            await db.commit()

            if done:
                return redirect_to_same_page("success", "Задача завершена")

            return redirect_to_same_page(
                "error",
                "Нельзя завершить задачу: сначала загрузите итоговый документ",
            )

        if action == "not_executed":
            if not (review_result and review_result.strip()):
                raise ValueError("Укажите причину, почему задача не выполнена")

            await ReportService.mark_task_as_not_executed(
                db,
                month_item_id=month_item_id,
                user_id=current_user_id,
                review_result=review_result,
                notes=evidence_note,
            )
            await db.commit()
            return redirect_to_same_page("success", "Задача отмечена как не выполненная")

        raise ValueError("Неизвестное действие")

    except ValueError as e:
        await db.rollback()

        if action == "save":
            return redirect_to_list("error", str(e))

        return redirect_to_same_page("error", str(e))

    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.exception("ERROR in staff_task_execute_save: %s", e)
        raise


@router.get(
    "/documents/{document_id}/view",
    name="staff_report_document_view",
)
async def staff_report_document_view(
        document_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    document = await ReportRepo.get_document_by_id(
        db,
        document_id=document_id,
    )
    if not document:
        raise ValueError("Документ не найден")

    task = await ReportService.get_task_for_execution(
        db,
        month_item_id=document.month_item_id,
        user_id=user.id,
    )

    if not task:
        raise ValueError("Нет доступа к документу")

    if not document.file_path:
        raise ValueError("Файл документа не найден")

    file_path_value = document.file_path
    if not file_path_value:
        raise ValueError("Файл документа не найден")

    file_path = Path(str(file_path_value))
    return FileResponse(
        path=str(file_path),
        media_type=document.mime_type or "application/octet-stream",
        filename=document.original_file_name or file_path.name,
        content_disposition_type="inline",
    )


@router.get(
    "/documents/{document_id}/download",
    name="staff_report_document_download",
)
async def staff_report_document_download(
        document_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    document = await ReportRepo.get_document_by_id(
        db,
        document_id=document_id,
    )
    if not document:
        raise ValueError("Документ не найден")

    task = await ReportService.get_task_for_execution(
        db,
        month_item_id=document.month_item_id,
        user_id=user.id,
    )

    if not task:
        raise ValueError("Нет доступа к документу")

    file_path_value = document.file_path

    if not file_path_value:
        raise ValueError("Файл документа не найден")

    file_path = Path(str(file_path_value))

    if not file_path.exists():
        raise ValueError("Файл отсутствует на диске")

    return FileResponse(
        path=str(file_path),
        media_type=document.mime_type or "application/octet-stream",
        filename=document.original_file_name or file_path.name,
        content_disposition_type="attachment",
    )
