# app/modules/monitoring/staff_rating_web.py

# app/modules/monitoring/routes.py

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.i18n import resolve_language, translate
from app.db.session import get_db
from app.modules.monitoring.monitoring_service import StaffMonitoringService
from app.modules.statistics.school_statistics_service import (
    SchoolPlanStatisticsService,
)
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates


router = APIRouter(
    prefix="/monitoring",
    tags=["Monitoring.School.Web"],
)


@router.get(
    "/staff-rating",
    response_class=HTMLResponse,
    name="staff_monitoring_rating_page",
)
async def staff_monitoring_rating_page(
    request: Request,
    month_plan_id: int | None = None,
    direction_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(
        require_roles(UserRole.SCHOOL_ADMIN)
    ),
):
    """
    Рейтинг исполнителей школы.

    Поддерживает фильтрацию:
    - по месячному плану;
    - по направлению ВШК.
    """

    school_plan = (
        await SchoolPlanStatisticsService.get_active_school_plan(
            db,
            school_id=user.school_id,
        )
    )

    if school_plan is None:
        raise HTTPException(
            status_code=404,
            detail=translate("Активный план школы не найден", resolve_language(request, user)),
        )

    page_data = await StaffMonitoringService.get_page_data(
        db,
        school_plan_id=school_plan.id,
        academic_year=school_plan.academic_year,
        month_plan_id=month_plan_id,
        direction_id=direction_id,
    )

    return render(
        templates,
        request,
        "monitoring/staff_rating.html",
        {
            "user": user,
            "school_name": school_plan.school.name,
            "academic_year": school_plan.academic_year,
            "page_data": page_data,
            "rating_rows": page_data.rating_rows,
            "totals": page_data.totals,
            "selected_month_plan_id": (
                page_data.selected_month_plan_id
            ),
            "selected_direction_id": (
                page_data.selected_direction_id
            ),
        },
    )
