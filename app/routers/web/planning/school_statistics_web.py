# app/routers/web/planning/school_statistics.py
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse

from app.db.session import get_db
from app.modules.planning.services.school_statistics_service import SchoolPlanStatisticsService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router = APIRouter(prefix="/planning/school", tags=["Planning.School.Web"])


@router.get(
    "/statistics",
    response_class=HTMLResponse,
    name="school_plan_statistics_page",
)
async def school_plan_statistics_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    # получаем активный план школы
    school_plan = await SchoolPlanStatisticsService.get_active_school_plan(
        db,
        school_id=user.school_id,
    )

    if school_plan is None:
        raise HTTPException(status_code=404, detail="План школы не найден")

    data = await SchoolPlanStatisticsService.get_statistics_page_data(
        db,
        school_plan_id=school_plan.id,
    )

    return render(
        templates,
        request,
        "planning/school/statistics.html",
        {
            "user": user,
            "plan_id": school_plan.id,
            "school_name": school_plan.school.name,
            "academic_year": school_plan.academic_year,
            "period_stats": data["period_stats"],
            "planned_stats": data["planned_stats"],
            "review_place_stats": data["review_place_stats"],
            "total_planned_count": data["total_planned_count"],
            "review_place_totals": data["review_place_totals"],
            "total_review_places_count": data["total_review_places_count"],
            "comparison_stats": data["comparison_stats"],
            "comparison_summary": data["comparison_summary"],
        },
    )
