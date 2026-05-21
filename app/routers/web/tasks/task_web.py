import json
from datetime import date
from urllib.parse import quote
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.db.session import get_db
from app.modules.reports.report_schemas import ExecutionFormDTO
from app.modules.tasks.service_task import StaffTasksService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.helpers.render import render
from app.routers.web.jinja_filters import MONTH_NAMES_KZ
from app.routers.web.web_common import templates

router = APIRouter(prefix="/staff/tasks", tags=["staff-tasks"])


@router.get("/", name="staff_tasks_page", response_class=HTMLResponse)
async def staff_tasks_page(
        request: Request,
        month: int | None = Query(default=None),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    target_month = month if month is not None else date.today().month

    if target_month < 1 or target_month > 12:
        raise HTTPException(status_code=400, detail="month must be 1..12")

    tasks = await StaffTasksService.get_my_tasks_page(
        db,
        user=user,
        month=target_month,
    )

    current_week = None
    if target_month == date.today().month:
        day = date.today().day
        current_week = ((day - 1) // 7) + 1

    return render(
        templates,
        request,
        "staff/tasks/school_staff_task.html",
        {
            "user": user,
            "tasks": tasks,
            "month": target_month,
            "current_week": current_week,
            "MONTH_NAMES": MONTH_NAMES_KZ,
        },
    )


@router.post("/take", name="take_task_to_work")
async def take_task_to_work(
        task_id: int = Form(...),
        month: int | None = Form(default=None),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    """
    Принять задачу в исполнение:
    - переводит статус задачи в IN_PROGRESS
    - при успехе сразу переводит пользователя на страницу исполнения задачи
    """
    redirect_month = month or date.today().month

    try:
        await StaffTasksService.take_task_to_work(
            db,
            user=user,
            month_item_id=task_id,
        )
    except HTTPException as exc:
        error_text = quote(str(exc.detail))
        return RedirectResponse(
            url=f"/staff/tasks?month={redirect_month}&error={error_text}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=(
            f"/staff/tasks/execute"
            f"?month={redirect_month}"
            f"&success=accepted"
            f"&accepted_task_id={task_id}"
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
        month: int | None = Query(default=None),
        selected_task_id: int | None = Query(default=None),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    target_month = month or date.today().month

    tasks = await StaffTasksService.get_in_progress_tasks_for_execution_page(
        db,
        user=user,
        month=target_month,
    )

    available_task_ids = {t.month_item_id for t in tasks}

    if selected_task_id is not None and selected_task_id not in available_task_ids:
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
        selected_task_id: int = Query(...),
        month: int | None = Query(default=None),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    target_month = month or date.today().month

    tasks = await StaffTasksService.get_in_progress_tasks_for_execution_page(
        db,
        user=user,
        month=target_month,
    )

    available_task_ids = {t.month_item_id for t in tasks}
    if selected_task_id not in available_task_ids:
        raise HTTPException(status_code=404, detail="Задача недоступна")

    payload = await StaffTasksService.get_execution_page_payload(
        db,
        user=user,
        month_item_id=selected_task_id,
    )

    control_flow_data = payload.control_flow or {}

    form_state = payload.execution or ExecutionFormDTO()
    state_json = json.dumps(asdict(form_state), ensure_ascii=False)

    return render(
        templates,
        request,
        "staff/partials/task_execute_details.html",
        {
            "selected_task": payload.selected_task,
            "selected_task_id": selected_task_id,
            "execution": payload.execution,
            "control_flow": control_flow_data,
            "month": target_month,
            "user": user,
            "today": date.today(),
            "current_draft": payload.current_draft,
            "state_json": state_json,
        },
    )
