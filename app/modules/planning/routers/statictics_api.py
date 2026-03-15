# app/routers/api/statistics.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.planning.services.school_statistics_service import SchoolPlanStatisticsService

router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get("/school-plan/{school_plan_id}")
async def school_plan_statistics(
    school_plan_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Статистика годового плана школы.

    Возвращает:
    - статистику по типам периодов
    - расчетную статистику плановой нагрузки
    """

    data = await SchoolPlanStatisticsService.get_statistics_page_data(
        db,
        school_plan_id=school_plan_id,
    )

    return {
        "school_plan_id": school_plan_id,
        "total_planned_count": data["total_planned_count"],
        "period_stats": [
            {
                "direction_id": item.direction_id,
                "direction_name": item.direction_name,
                "month": item.month_count,
                "months": item.months_count,
                "monthly": item.monthly_count,
                "quarter": item.quarter_count,
                "all_year": item.all_year_count,
            }
            for item in data["period_stats"]
        ],
        "planned_stats": [
            {
                "direction_id": item.direction_id,
                "direction_name": item.direction_name,
                "planned_count": item.planned_count,
            }
            for item in data["planned_stats"]
        ],
    }