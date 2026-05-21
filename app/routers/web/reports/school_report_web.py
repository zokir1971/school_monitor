# app/routers/web/reports/school_report_web.py
from __future__ import annotations

from pathlib import Path
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse

from app.db.session import get_db
from app.modules.planning.enums import PlanItemStatus
from app.modules.reports.enums import DocumentType, TaskCompletionMode
from app.modules.reports.report_repo import ReportRepo
from app.modules.reports.report_service import ReportService
from app.modules.users.deps import require_roles, get_current_user
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.web_common import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/staff/reports", tags=["staff-reports"])

STORAGE_ROOT = Path("storage")


# Сохранение черновика
@router.post("/staff/reports/{month_item_id}/execute/save", name="staff_task_execute_save")
async def staff_task_execute_save(
        request: Request,
        month_item_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    form = await request.form()

    action = str(form.get("action") or "").strip()

    month = str(form.get("month") or "").strip()
    selected_task_id = str(form.get("selected_task_id") or "").strip()

    # -------------------------
    # SAVE (сохранение черновика)
    # -------------------------
    if action == "save":
        await ReportService.save_execution_draft(
            db,
            month_item_id=month_item_id,
            user_id=current_user.id,
            control_scope=str(form.get("control_scope") or "").strip(),
            control_form=str(form.get("control_form") or "").strip(),
            control_kind=str(form.get("control_kind") or "").strip(),
            review_result=str(form.get("review_result") or "").strip(),
            report_types=[str(x).strip() for x in form.getlist("report_types") if str(x).strip()],
            subjects=[str(x).strip() for x in form.getlist("subjects") if str(x).strip()],
            class_groups=[str(x).strip() for x in form.getlist("class_groups") if str(x).strip()],
            parallel_classes=[str(x).strip() for x in form.getlist("parallel_classes") if str(x).strip()],
            teacher_ids=[str(x).strip() for x in form.getlist("teacher_ids") if str(x).strip()],
            teacher_id=str(form.get("teacher_id") or "").strip(),
        )

        redirect_url = request.url_for("staff_tasks_execute_page")

        query_parts: list[str] = [
            "success=saved",
        ]

    # -------------------------
    # FINISH (переход к завершению)
    # -------------------------
    elif action == "finish":
        return RedirectResponse(
            url=request.url_for(
                "staff_report_execute_page",
                month_item_id=month_item_id
            ),
            status_code=303,
        )

    else:
        raise HTTPException(status_code=400, detail="Неподдерживаемое действие.")

    # -------------------------
    # Общая часть редиректа (для save)
    # -------------------------
    if selected_task_id:
        query_parts.append(f"selected_task_id={selected_task_id}")
    else:
        query_parts.append(f"selected_task_id={month_item_id}")

    if month:
        query_parts.append(f"month={month}")

    location = f"{redirect_url}?{'&'.join(query_parts)}"

    return RedirectResponse(
        url=location,
        status_code=303,
    )


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
    month = request.query_params.get("month")
    page_data = None

    try:
        page_data = await ReportService.get_execution_page_data(
            db,
            month_item_id=month_item_id,
            user_id=user.id,
        )
    except ValueError as e:
        return templates.TemplateResponse(
            "staff/reports/report_execute.html",
            {
                "request": request,
                "user": user,
                "task": None,
                "task_topic": None,
                "task_goal": None,
                "review_place_text": None,
                "execution": None,

                "is_done": page_data.get("is_done", False),
                "current_final_document": page_data.get("current_final_document"),
                "has_final_document": page_data.get("has_final_document", False),
                "final_document_status": page_data.get("final_document_status"),

                "required_documents": [],
                "final_documents": [],

                "completion_ready": False,
                "completion_modes": TaskCompletionMode,

                "month": month,

                "error": str(e),
                "success": None,
                "warning": None,
            },
            status_code=404,
        )

    task = page_data["task"]

    task_status_value = getattr(task.status, "value", task.status)
    is_done = task_status_value == PlanItemStatus.DONE.value

    return templates.TemplateResponse(
        "staff/reports/report_execute.html",
        {
            "request": request,
            "user": user,
            "task": task,
            "task_topic": page_data["task_topic"],
            "task_goal": page_data["task_goal"],
            "review_place_text": page_data["review_place_text"],
            "execution": page_data["execution"],

            "required_documents": page_data["required_documents"],
            "final_documents": page_data["final_documents"],
            "current_final_document": (
                page_data["final_documents"][0]
                if page_data["final_documents"]
                else None
            ),

            "completion_ready": page_data["completion_ready"],

            "is_done": is_done,
            "task_status": task.status,
            "task_status_value": task_status_value,

            "completion_modes": TaskCompletionMode,
            "month": month,

            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
            "warning": request.query_params.get("warning"),
        },
    )


# Завершение и отправка на рассмотрения
@router.post(
    "/{month_item_id}/execute",
    name="staff_report_execute_submit",
)
async def staff_report_execute_submit(
        request: Request,
        month_item_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    form = await request.form()
    action = str(form.get("action") or "").strip()
    base_url = str(request.url_for("staff_report_execute_page", month_item_id=month_item_id))

    try:
        if action == "upload_final":
            upload_file = form.get("reference_file")
            required_document_id_raw = form.get("required_document_id")

            if upload_file is None or not getattr(upload_file, "filename", ""):
                return RedirectResponse(
                    url=f"{base_url}?error=Выберите файл для загрузки.",
                    status_code=303,
                )

            required_document_id = None

            if required_document_id_raw not in (None, ""):
                required_document_id = int(required_document_id_raw)

            completion_mode_raw = str(
                form.get("completion_mode") or ""
            ).strip()

            if not completion_mode_raw:
                return RedirectResponse(
                    url=f"{base_url}?error=Выберите вариант завершения.",
                    status_code=303,
                )

            try:
                completion_mode = TaskCompletionMode(completion_mode_raw)
            except ValueError:
                return RedirectResponse(
                    url=f"{base_url}?error=Выберите корректный вариант завершения.",
                    status_code=303,
                )

            await ReportService.upload_final_document(
                db,
                month_item_id=month_item_id,
                user_id=user.id,
                required_document_id=required_document_id,
                upload_file=upload_file,
                document_type=DocumentType.REFERENCE,
            )

            await ReportService.complete_task_execution(
                db,
                month_item_id=month_item_id,
                user_id=user.id,
                completion_mode=completion_mode,
            )

            return RedirectResponse(
                url=f"{base_url}?success=Итоговый документ загружен. Задача завершена и отправлена на рассмотрение.",
                status_code=303,
            )

        if action == "done":
            completion_mode_raw = str(form.get("completion_mode") or "").strip()

            if not completion_mode_raw:
                return RedirectResponse(
                    url=f"{base_url}?error=Выберите вариант завершения.",
                    status_code=303,
                )

            try:
                completion_mode = TaskCompletionMode(completion_mode_raw)
            except ValueError:
                return RedirectResponse(
                    url=f"{base_url}?error=Выберите корректный вариант завершения.",
                    status_code=303,
                )

            await ReportService.complete_task_execution(
                db,
                month_item_id=month_item_id,
                user_id=user.id,
                completion_mode=completion_mode,
            )

            return RedirectResponse(
                url=f"{base_url}?success=Задача завершена и отправлена на рассмотрение.",
                status_code=303,
            )

        return RedirectResponse(
            url=f"{base_url}?error=Неподдерживаемое действие.",
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
            "Ошибка файловой системы при обработке действия: month_item_id=%s, user_id=%s, action=%s",
            month_item_id,
            user.id,
            action,
        )
        return RedirectResponse(
            url=f"{base_url}?error=Ошибка при работе с файлом.",
            status_code=303,
        )

    except SQLAlchemyError:
        logger.exception(
            "Ошибка БД при обработке действия: month_item_id=%s, user_id=%s, action=%s",
            month_item_id,
            user.id,
            action,
        )
        return RedirectResponse(
            url=f"{base_url}?error=Ошибка при сохранении данных.",
            status_code=303,
        )


# Просмотр итогового документа
@router.get("/documents/{document_id}/view", name="staff_report_document_view")
async def staff_report_document_view(
        document_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    document = await ReportRepo.get_document_by_id(
        db,
        document_id=document_id,
    )

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Документ не найден",
        )

    has_access = await ReportRepo.user_has_access_to_month_item(
        db,
        month_item_id=document.month_item_id,
        user_id=current_user.id,
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к документу",
        )

    file_path = str(document.file_path or "").strip()

    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="У документа отсутствует путь к файлу",
        )

    normalized_path = file_path.replace("\\", "/")
    path_obj = Path(normalized_path)

    candidate_paths = []

    if path_obj.is_absolute():
        candidate_paths.append(path_obj)
    else:
        candidate_paths.append(Path("storage") / path_obj)
        candidate_paths.append(path_obj)

    abs_path = next((p for p in candidate_paths if p.exists()), None)

    if abs_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                    "Файл не найден на диске. Проверены пути: "
                    + ", ".join(str(p) for p in candidate_paths)
            ),
        )

    display_name = (
            document.original_file_name
            or document.stored_file_name
            or f"document_{document.id}.pdf"
    )

    media_type = str(document.mime_type or "").strip().lower()
    if not media_type or media_type == "application/octet-stream":
        if file_path.lower().endswith(".pdf"):
            media_type = "application/pdf"
        else:
            media_type = "application/octet-stream"

    response = FileResponse(
        path=str(abs_path),
        media_type=media_type,
    )

    quoted_name = quote(display_name)
    response.headers["Content-Disposition"] = (
        f"inline; filename*=UTF-8''{quoted_name}"
    )

    return response


# Выгрузка итогового документа
@router.get("/documents/{document_id}/download", name="staff_report_document_download")
async def staff_report_document_download(
        document_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    document = await ReportRepo.get_document_by_id(db, document_id=document_id)

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Документ не найден",
        )

    has_access = await ReportRepo.user_has_access_to_month_item(
        db,
        month_item_id=document.month_item_id,
        user_id=current_user.id,
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к документу",
        )

    file_path = str(document.file_path or "").strip()

    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="У документа отсутствует путь к файлу",
        )

    normalized_path = file_path.replace("\\", "/")
    path_obj = Path(normalized_path)

    candidate_paths = []

    if path_obj.is_absolute():
        candidate_paths.append(path_obj)
    else:
        candidate_paths.append(Path("storage") / path_obj)
        candidate_paths.append(path_obj)

    abs_path = next((p for p in candidate_paths if p.exists()), None)

    if abs_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                    "Файл не найден на диске. Проверены пути: "
                    + ", ".join(str(p) for p in candidate_paths)
            ),
        )

    return FileResponse(
        path=str(abs_path),
        media_type=document.mime_type or "application/octet-stream",
        filename=(
                document.original_file_name
                or document.stored_file_name
                or f"document_{document.id}"
        ),
    )
