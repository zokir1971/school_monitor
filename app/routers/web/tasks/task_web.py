# app/routers/web/tasks/tasks_web.py
import json
from dataclasses import asdict
from datetime import date
from urllib.parse import urlencode, quote

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.db.session import get_db
from app.modules.reports.report_schemas import ExecutionFormDTO
from app.modules.reports.schemas.report_assignment_dto import ReportAssignmentInputDTO
from app.modules.reports.services.report_assignment_service import ReportAssignmentService
from app.modules.tasks.task_service import StaffTasksService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.helpers.render import render
from app.routers.web.jinja_filters import MONTH_NAMES_KZ
from app.routers.web.web_common import templates

router = APIRouter(
    prefix="/staff/tasks",
    tags=["staff-tasks"],
)


def _current_month() -> int:
    return date.today().month


def _url_with_query(
        base_url: str,
        **params: object,
) -> str:
    """
    Добавить query-параметры к URL.

    Пустые значения не включаются. Текстовые сообщения
    кодируются через urlencode.
    """

    query_params = {
        key: value
        for key, value in params.items()
        if value is not None and value != ""
    }

    if not query_params:
        return base_url

    return f"{base_url}?{urlencode(query_params)}"


@router.get(
    "/",
    name="staff_tasks_page",
    response_class=HTMLResponse,
)
async def staff_tasks_page(
        request: Request,
        month: int | None = Query(
            default=None,
            ge=1,
            le=12,
        ),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    """
    Страница задач сотрудника за выбранный месяц.
    """

    target_month = (
        month
        if month is not None
        else _current_month()
    )

    primary_tasks, co_executor_tasks = (
        await StaffTasksService.get_my_tasks_page(
            db,
            user=user,
            month=target_month,
        )
    )

    today = date.today()
    current_week: int | None = None

    if target_month == today.month:
        current_week = ((today.day - 1) // 7) + 1

    return render(
        templates,
        request,
        "staff/tasks/school_staff_task.html",
        {
            "user": user,
            "primary_tasks": primary_tasks,
            "co_executor_tasks": co_executor_tasks,
            "month": target_month,
            "current_week": current_week,
            "MONTH_NAMES": MONTH_NAMES_KZ,
        },
    )


@router.post(
    "/take",
    name="take_task_to_work",
)
async def take_task_to_work(
        task_id: int = Form(..., gt=0),
        month: int | None = Form(
            default=None,
            ge=1,
            le=12,
        ),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    """
    Принять задачу в исполнение.

    В одной транзакции:

    - задача переводится в IN_PROGRESS;
    - уведомление ответственного переводится в ACCEPTED;
    - изменения фиксируются через commit.
    """

    redirect_month = (
        month
        if month is not None
        else _current_month()
    )

    try:
        await StaffTasksService.take_task_to_work(
            db,
            user=user,
            month_item_id=task_id,
        )

        # Обязательно: сохраняет и статус задачи,
        # и изменение уведомления SENT -> ACCEPTED.
        await db.commit()

    except HTTPException as exc:
        await db.rollback()

        error_text = quote(
            str(exc.detail),
            safe="",
        )

        return RedirectResponse(
            url=(
                f"/staff/tasks/"
                f"?month={redirect_month}"
                f"&error={error_text}"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    except Exception:
        await db.rollback()
        raise

    return RedirectResponse(
        url=(
            f"/staff/tasks/execute"
            f"?month={redirect_month}"
            f"&selected_task_id={task_id}"
            f"&success=accepted"
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get(
    "/execute",
    name="staff_tasks_execute_page",
    response_class=HTMLResponse,
)
async def staff_tasks_execute_page(
        request: Request,
        month: int | None = Query(
            default=None,
            ge=1,
            le=12,
        ),
        selected_task_id: int | None = Query(
            default=None,
            gt=0,
        ),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    """
    Страница исполнения с перечнем задач IN_PROGRESS.
    """

    target_month = (
        month
        if month is not None
        else _current_month()
    )

    tasks = (
        await StaffTasksService
        .get_in_progress_tasks_for_execution_page(
            db,
            user=user,
            month=target_month,
        )
    )

    available_task_ids = {
        task.month_item_id
        for task in tasks
    }

    if (
            selected_task_id is not None
            and selected_task_id not in available_task_ids
    ):
        selected_task_id = None

    return render(
        templates,
        request,
        "staff/tasks/task_execute.html",
        {
            "tasks": tasks,
            "selected_task": None,
            "selected_task_id": selected_task_id,
            "month": target_month,
            "user": user,
            "today": date.today(),
        },
    )


@router.get(
    "/execute/details",
    name="staff_task_execute_details",
    response_class=HTMLResponse,
)
async def staff_task_execute_details(
        request: Request,
        selected_task_id: int = Query(..., gt=0),
        month: int | None = Query(
            default=None,
            ge=1,
            le=12,
        ),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    """
    Загрузить содержимое выбранной задачи для execution-страницы.

    Доступ к конкретной задаче проверяется внутри
    StaffTasksService.get_execution_page_payload().
    Поэтому повторная загрузка всего списка задач здесь не нужна.
    """

    target_month = (
        month
        if month is not None
        else _current_month()
    )

    payload = await StaffTasksService.get_execution_page_payload(
        db,
        user=user,
        month_item_id=selected_task_id,
    )

    selected_task = payload.selected_task

    if selected_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или недоступна.",
        )

    if selected_task.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Задача не находится в процессе исполнения.",
        )

    control_flow_data = payload.control_flow or {}
    form_state = payload.execution or ExecutionFormDTO()

    state_json = json.dumps(
        asdict(form_state),
        ensure_ascii=False,
    )

    return render(
        templates,
        request,
        "staff/partials/task_execute_details.html",
        {
            "selected_task": selected_task,
            "selected_task_id": selected_task_id,
            "execution": form_state,
            "control_flow": control_flow_data,
            "month": target_month,
            "user": user,
            "today": date.today(),
            "current_draft": payload.current_draft,
            "state_json": state_json,
        },
    )


def _parse_report_assignment_form(
        form_data,
) -> list[ReportAssignmentInputDTO]:
    """
    Преобразовать динамические поля формы вида:

        assignment_<selected_report_id>=<staff_member_id>

    в список DTO сервисного слоя.

    Повтор одного selected_report_id считается ошибкой.
    Пустой staff_member_id запрещён.
    """

    assignments: list[ReportAssignmentInputDTO] = []
    seen_report_ids: set[int] = set()

    for field_name, raw_staff_member_id in form_data.multi_items():
        if not field_name.startswith("assignment_"):
            continue

        raw_selected_report_id = field_name.removeprefix(
            "assignment_"
        ).strip()

        try:
            selected_report_id = int(
                raw_selected_report_id
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Получен некорректный идентификатор "
                    "выбранного отчёта."
                ),
            ) from exc

        staff_member_text = str(
            raw_staff_member_id or ""
        ).strip()

        if not staff_member_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Назначьте исполнителя каждому "
                    "выбранному отчёту."
                ),
            )

        try:
            staff_member_id = int(
                staff_member_text
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Получен некорректный идентификатор "
                    "исполнителя отчёта."
                ),
            ) from exc

        if selected_report_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Идентификатор выбранного отчёта "
                    "должен быть положительным числом."
                ),
            )

        if staff_member_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Идентификатор исполнителя отчёта "
                    "должен быть положительным числом."
                ),
            )

        if selected_report_id in seen_report_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Один выбранный отчёт передан "
                    "в форме несколько раз."
                ),
            )

        seen_report_ids.add(
            selected_report_id
        )

        assignments.append(
            ReportAssignmentInputDTO(
                selected_report_id=selected_report_id,
                staff_member_id=staff_member_id,
            )
        )

    if not assignments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "В форме отсутствуют отчёты "
                "для распределения."
            ),
        )

    return assignments


@router.get(
    "/{month_item_id}/report-assignments",
    name="staff_report_assignments_page",
    response_class=HTMLResponse,
)
async def staff_report_assignments_page(
        request: Request,
        month_item_id: int,
        month: int = Query(
            default=1,
            ge=1,
            le=12,
        ),
        success: str | None = Query(
            default=None,
        ),
        error: str | None = Query(
            default=None,
        ),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    """
    Показать страницу распределения выбранных отчётов.
    """

    try:
        page_data = await (
            ReportAssignmentService
            .get_assignment_page(
                db,
                user=user,
                month_item_id=month_item_id,
                month=month,
            )
        )

    except HTTPException as exc:
        tasks_page_url = str(
            request.url_for(
                "staff_tasks_page"
            )
        )

        return RedirectResponse(
            url=_url_with_query(
                tasks_page_url,
                month=month,
                error=str(exc.detail),
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return render(
        templates,
        request,
        "staff/reports/report_assignments.html",
        {
            "user": user,
            "page_data": page_data,
            "task": page_data,
            "month_item_id": month_item_id,
            "month": month,
            "executors": page_data.executors,
            "reports": page_data.reports,
            "success": success,
            "error": error,
        },
    )


@router.post(
    "/{month_item_id}/report-assignments",
    name="staff_report_assignments_save",
)
async def staff_report_assignments_save(
        request: Request,
        month_item_id: int,
        month: int = Form(
            ...,
            ge=1,
            le=12,
        ),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    """
    Сохранить распределение выбранных отчётов.
    """

    assignment_page_url = str(
        request.url_for(
            "staff_report_assignments_page",
            month_item_id=month_item_id,
        )
    )

    try:
        form_data = await request.form()

        assignments = _parse_report_assignment_form(
            form_data
        )

        result = await (
            ReportAssignmentService
            .save_assignments(
                db,
                user=user,
                month_item_id=month_item_id,
                assignments=assignments,
            )
        )

        await db.commit()

    except HTTPException as exc:
        await db.rollback()

        return RedirectResponse(
            url=_url_with_query(
                assignment_page_url,
                month=month,
                error=str(exc.detail),
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    except Exception:
        await db.rollback()
        raise

    templates_page_url = str(
        request.url_for(
            "staff_report_templates_page",
            month_item_id=month_item_id,
        )
    )

    success_text = (
        "Распределение отчётов сохранено. "
        f"Создано: {result.created_count}, "
        f"изменено: {result.updated_count}, "
        f"без изменений: {result.unchanged_count}."
    )

    return RedirectResponse(
        url=_url_with_query(
            templates_page_url,
            month=month,
            success=success_text,
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ============================================================
# REPORT ASSIGNMENT ACTIONS
# ============================================================


@router.post(
    "/{month_item_id}/report-assignments/"
    "{selected_report_id}/reassign",
    name="staff_report_assignment_reassign",
)
async def staff_report_assignment_reassign(
        request: Request,
        month_item_id: int,
        selected_report_id: int,
        month: int = Form(
            ...,
            ge=1,
            le=12,
        ),
        staff_member_id: int = Form(
            ...,
            gt=0,
        ),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    """
    Переназначить один выбранный системный отчёт.

    Операция разрешена только ответственному PRIMARY.
    Новый исполнитель должен быть назначен на эту задачу
    как PRIMARY или CO_EXECUTOR.

    Commit выполняется здесь — на границе web-транзакции.
    """

    assignment_page_url = str(
        request.url_for(
            "staff_report_assignments_page",
            month_item_id=month_item_id,
        )
    )

    try:
        await ReportAssignmentService.reassign_report(
            db,
            user=user,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            staff_member_id=staff_member_id,
        )

        await db.commit()

    except HTTPException as exc:
        await db.rollback()

        return RedirectResponse(
            url=_url_with_query(
                assignment_page_url,
                month=month,
                error=str(exc.detail),
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    except Exception:
        await db.rollback()
        raise

    return RedirectResponse(
        url=_url_with_query(
            assignment_page_url,
            month=month,
            success="Исполнитель отчёта переназначен.",
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/{month_item_id}/report-assignments/"
    "{selected_report_id}/waive",
    name="staff_report_assignment_waive",
)
async def staff_report_assignment_waive(
        request: Request,
        month_item_id: int,
        selected_report_id: int,
        month: int = Form(
            ...,
            ge=1,
            le=12,
        ),
        reason: str = Form(
            ...,
            min_length=1,
            max_length=2000,
        ),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    """
    Освободить один системный отчёт от обязательного выполнения.

    Причина обязательна.
    Операция разрешена только ответственному PRIMARY.

    Commit выполняется здесь — на границе web-транзакции.
    """

    assignment_page_url = str(
        request.url_for(
            "staff_report_assignments_page",
            month_item_id=month_item_id,
        )
    )

    try:
        await ReportAssignmentService.waive_report(
            db,
            user=user,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            reason=reason,
        )

        await db.commit()

    except HTTPException as exc:
        await db.rollback()

        return RedirectResponse(
            url=_url_with_query(
                assignment_page_url,
                month=month,
                error=str(exc.detail),
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    except Exception:
        await db.rollback()
        raise

    return RedirectResponse(
        url=_url_with_query(
            assignment_page_url,
            month=month,
            success=(
                "Отчёт освобождён от обязательного выполнения. "
                "Причина сохранена."
            ),
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )
