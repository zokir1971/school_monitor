# app/routers/web/planning/month_plan_assignee_web.py

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.responses import HTMLResponse, RedirectResponse

from app.db.session import get_db
from app.modules.planning.services.month_plan_assignee_service import (
    SchoolMonthPlanAssigneeService,
)
from app.modules.staff.utils.staff_require_school import require_school_id
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates


router = APIRouter(
    prefix="/planning/school",
    tags=["planning-school-month-assignees"],
)


@router.get(
    "/monthly/{month_item_id}/assignees",
    name="school_month_item_assignees",
    response_class=HTMLResponse,
)
async def school_month_item_assignees_page(
    request: Request,
    month_item_id: int,
    success: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(
        require_roles(UserRole.SCHOOL_ADMIN)
    ),
):
    """
    Страница назначения исполнителей задачи месячного плана.

    Основной исполнитель выбирается среди сотрудников,
    соответствующих ответственным ролям годового плана.

    Соисполнителями могут быть любые активные сотрудники школы,
    имеющие активную SchoolStaffRole.
    """

    school_id = require_school_id(user)

    page_data = (
        await SchoolMonthPlanAssigneeService
        .get_assignment_page_data(
            db,
            school_id=school_id,
            month_item_id=month_item_id,
        )
    )

    if page_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача месячного плана не найдена.",
        )

    return render(
        templates,
        request,
        "planning/school/month_item_assignees.html",
        {
            "user": user,
            "dto": page_data,

            # Основные сведения о задаче.
            "month_item_id": page_data.month_item_id,
            "row11_id": page_data.row11_id,
            "direction_name": page_data.direction_name,
            "topic": page_data.topic,
            "goal": page_data.goal,
            "week_of_month": page_data.week_of_month,
            "planned_start": page_data.planned_start,
            "planned_end": page_data.planned_end,
            "is_included": page_data.is_included,
            "can_assign": page_data.can_assign,

            # Новая архитектура назначения.
            "primary_groups": page_data.primary_groups,
            "planned_co_executor_groups": (
                page_data.planned_co_executor_groups
            ),
            "additional_co_executor_groups": (
                page_data.additional_co_executor_groups
            ),
            "assigned_participants": (
                page_data.assigned_participants
            ),
            "selected_primary_staff_role_id": (
                page_data.selected_primary_staff_role_id
            ),
            "selected_co_executor_staff_role_ids": (
                page_data.selected_co_executor_staff_role_ids
            ),

            "success": success,
            "error": error,
        },
    )


@router.post(
    "/monthly/{month_item_id}/assignees",
    name="school_month_item_assignees_save",
)
async def school_month_item_assignees_save(
    request: Request,
    month_item_id: int,
    primary_staff_role_id: int | None = Form(default=None),
    co_executor_staff_role_ids: list[int] = Form(default=[]),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(
        require_roles(UserRole.SCHOOL_ADMIN)
    ),
):
    """
    Сохранить назначения задачи месячного плана.

    После успешного сохранения пользователь возвращается
    на страницу соответствующего месячного плана.
    """

    school_id = require_school_id(user)

    try:
        month, school_plan_id = (
            await SchoolMonthPlanAssigneeService
            .save_assignments(
                db,
                school_id=school_id,
                month_item_id=month_item_id,
                primary_staff_role_id=primary_staff_role_id,
                co_executor_staff_role_ids=(
                    co_executor_staff_role_ids
                ),
                assigned_by_user_id=user.id,
            )
        )

        await db.commit()

    except HTTPException as exc:
        await db.rollback()

        error_text = quote(
            str(exc.detail),
            safe="",
        )

        page_url = request.url_for(
            "school_month_item_assignees",
            month_item_id=month_item_id,
        )

        return RedirectResponse(
            url=f"{page_url}?error={error_text}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    except Exception:
        await db.rollback()
        raise

    success_text = quote(
        "Исполнители успешно назначены.",
        safe="",
    )

    monthly_page_url = request.url_for(
        "school_monthly_page"
    )

    return RedirectResponse(
        url=(
            f"{monthly_page_url}"
            f"?month={month}"
            f"&school_plan_id={school_plan_id}"
            f"&success={success_text}"
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )
