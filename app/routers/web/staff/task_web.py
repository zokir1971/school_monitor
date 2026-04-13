from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.db.session import get_db
from app.modules.planning.control_flow import build_control_flow_for_ui
from app.modules.reports.report_repo import ReportRepo
from app.modules.reports.report_services import ReportService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.modules.staff.service_task import StaffTasksService
from app.routers.web.web_common import templates
from app.routers.web.helpers.render import render
from app.routers.web.jinja_filters import MONTH_NAMES_KZ

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
        "staff/school_staff_task.html",
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
    - переводит статус задачи TODO -> IN_PROGRESS
    - перенаправляет на страницу исполнения задачи
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
        url=f"/staff/tasks/execute?selected_task_id={task_id}&month={redirect_month}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get(
    "/execute",
    name="staff_tasks_execute_page",
    response_class=HTMLResponse,
)
async def staff_tasks_execute_page(
    request: Request,
    selected_task_id: int | None = Query(default=None),
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

    selected_task = None

    if selected_task_id:
        selected_task = await StaffTasksService.get_task_for_execution(
            db,
            user=user,
            month_item_id=selected_task_id,
        )
    elif tasks:
        selected_task_id = tasks[0].month_item_id
        selected_task = await StaffTasksService.get_task_for_execution(
            db,
            user=user,
            month_item_id=selected_task_id,
        )

    current_draft = None
    execution = None

    if selected_task:
        current_draft = await ReportRepo.get_current_draft(
            db,
            month_item_id=selected_task_id,
        )

        execution_data = await ReportRepo.get_execution_data_for_task(
            db,
            month_item_id=selected_task_id,
        )
        execution = ReportService.build_execution_template_data(execution_data)

    control_flow = build_control_flow_for_ui()

    return render(
        templates,
        request,
        "staff/task_execute.html",
        {
            "tasks": tasks,
            "selected_task": selected_task,
            "selected_task_id": selected_task_id,
            "execution": execution,
            "control_flow": control_flow,
            "month": target_month,
            "user": user,
            "today": date.today(),
            "current_draft": current_draft,
        },
    )


@router.post("/{month_item_id}/execute", name="staff_task_execute_save")
async def staff_task_execute_save(
        month_item_id: int,
        action: str = Form(...),
        month: int | None = Form(default=None),

        control_scope: str = Form(...),
        control_form: str = Form(...),
        control_kind: str = Form(...),
        report_types: list[str] = Form(...),

        executed_at: date | None = Form(default=None),

        evidence_note: str | None = Form(default=None),
        reference_text: str | None = Form(default=None),
        conclusion: str | None = Form(default=None),
        recommendations: str | None = Form(default=None),
        review_result: str | None = Form(default=None),
        planned_review_place: str | None = Form(default=None),

        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    """
    Сохранение исполнения задачи.

    action:
    - save
    - done
    - not_executed

    executed_at:
    - фактическая дата исполнения
    - используется при action == "done"
    """
    redirect_month = month or date.today().month

    try:
        await StaffTasksService.save_task_execution(
            db,
            user=user,
            month_item_id=month_item_id,
            action=action,
            executed_at=executed_at,
            control_scope=control_scope,
            control_form=control_form,
            control_kind=control_kind,
            report_types=report_types,
            evidence_note=evidence_note,
            reference_text=reference_text,
            conclusion=conclusion,
            recommendations=recommendations,
            review_result=review_result,
            planned_review_place=planned_review_place,
        )
    except HTTPException as exc:
        error_text = quote(str(exc.detail))
        return RedirectResponse(
            url=(
                f"/staff/tasks/execute"
                f"?selected_task_id={month_item_id}"
                f"&month={redirect_month}"
                f"&error={error_text}"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as exc:
        error_text = quote(f"Ошибка сохранения: {exc}")
        return RedirectResponse(
            url=(
                f"/staff/tasks/execute"
                f"?selected_task_id={month_item_id}"
                f"&month={redirect_month}"
                f"&error={error_text}"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    success_text = quote("Данные успешно сохранены")
    return RedirectResponse(
        url=(
            f"/staff/tasks/execute"
            f"?selected_task_id={month_item_id}"
            f"&month={redirect_month}"
            f"&success={success_text}"
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )
