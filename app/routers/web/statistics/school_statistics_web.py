# app/routers/web/statistics/school_statistics.py
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse

from app.core.i18n import resolve_language, translate
from app.db.session import get_db
from app.modules.statistics.school_statistics_service import SchoolPlanStatisticsService, \
    SchoolExecutionStatisticsService, StaffExecutionStatisticsService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router = APIRouter(
    prefix="/statistics",
    tags=["Statistics.School.Web"],
)


@router.get(
    "/",
    response_class=HTMLResponse,
    name="school_plan_statistics_page",
)
async def school_plan_statistics_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_plan = await SchoolPlanStatisticsService.get_active_school_plan(
        db,
        school_id=user.school_id,
    )

    if school_plan is None:
        raise HTTPException(
            status_code=404,
            detail=translate('Активный план школы не найден', resolve_language(request, user)),
        )

    data = await SchoolPlanStatisticsService.get_statistics_page_data(
        db,
        school_plan_id=school_plan.id,
    )

    school = getattr(school_plan, "school", None)

    return render(
        templates,
        request,
        "statistics/statistics_planning.html",
        {
            "user": user,
            "plan_id": school_plan.id,
            "school_name": (
                    getattr(school, "name", None)
                    or getattr(user, "school_name", None)
                    or translate("Школа", resolve_language(request, user))
            ),
            "academic_year": school_plan.academic_year,

            "period_stats": data["period_stats"],
            "planned_stats": data["planned_stats"],
            "review_place_stats": data["review_place_stats"],

            "total_planned_count": data["total_planned_count"],
            "review_place_totals": data["review_place_totals"],
            "total_review_places_count": data[
                "total_review_places_count"
            ],

            "comparison_stats": data["comparison_stats"],
            "comparison_summary": data["comparison_summary"],
        },
    )


@router.get(
    "/execution",
    response_class=HTMLResponse,
    name="school_execution_statistics_page",
)
async def school_execution_statistics_page(
        request: Request,
        month_plan_id: int | None = None,
        db: AsyncSession = Depends(get_db),
        user=Depends(
            require_roles(UserRole.SCHOOL_ADMIN)
        ),
):
    school_plan = (
        await SchoolPlanStatisticsService.get_active_school_plan(
            db,
            school_id=user.school_id,
        )
    )

    if school_plan is None:
        raise HTTPException(
            status_code=404,
            detail=translate('План школы не найден', resolve_language(request, user)),
        )

    data = (
        await SchoolExecutionStatisticsService
        .get_execution_page_data(
            db,
            school_plan_id=school_plan.id,
            selected_month_plan_id=month_plan_id,
        )
    )

    school = getattr(school_plan, "school", None)

    return render(
        templates,
        request,
        "statistics/statistics_execution.html",
        {
            "user": user,
            "plan_id": school_plan.id,
            "school_name": (
                    getattr(school, "name", None)
                    or translate("Школа", resolve_language(request, user))
            ),
            "academic_year": school_plan.academic_year,
            **data,
        },
    )


# ============================================================================
# Моя статистика сотрудника
# ============================================================================

@router.get(
    "/my",
    response_class=HTMLResponse,
    name="staff_statistics_page",
)
async def staff_statistics_page(
    request: Request,
    month_plan_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(
        require_roles(
            UserRole.SCHOOL_STAFF,
            UserRole.SCHOOL_ADMIN,
        )
    ),
):
    """
    Страница «Моя статистика».

    Отображает личную статистику выполнения задач
    текущего сотрудника.

    В статистику включаются задачи, где пользователь:

    • основной ответственный;
    • исполнитель;
    • соисполнитель.

    Страница состоит из трех блоков:

    1. Общие показатели за учебный год.
    2. Статистика по месяцам.
    3. Статистика выбранного месяца по направлениям ВШК.
    """

    # Получаем активный годовой план школы.
    school_plan = (
        await SchoolPlanStatisticsService.get_active_school_plan(
            db,
            school_id=user.school_id,
        )
    )

    if school_plan is None:
        raise HTTPException(
            status_code=404,
            detail=translate('Активный план школы не найден.', resolve_language(request, user)),
        )

    # Формируем всю статистику страницы.
    page_data = (
        await StaffExecutionStatisticsService.get_page_data(
            db,
            school_plan_id=school_plan.id,
            user_id=user.id,
            selected_month_plan_id=month_plan_id,
        )
    )

    staff_member = user.staff_member

    # Передаем данные в шаблон.

    return render(
        templates,
        request,
        "statistics/staff_statistics.html",
        {
            "user": user,

            "plan_id": school_plan.id,

            "school_name": school_plan.school.name,
            "academic_year": school_plan.academic_year,

            "staff_name": (
                staff_member.full_name
                if staff_member
                else ""
            ),

            "staff_position": (
                staff_member.position_text
                if staff_member
                else ""
            ),

            **page_data,
        },
    )
