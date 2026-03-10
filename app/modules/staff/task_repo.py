from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.models_month_plan import (
    SchoolMonthPlanItem,
    SchoolMonthPlan,
)
from app.modules.planning.models_month_plan import SchoolMonthPlanItemAssignee
from app.modules.planning.models_school import SchoolPlan


class StaffTasksRepo:

    @staticmethod
    async def list_tasks_for_staff(
        db: AsyncSession,
        *,
        school_id: int,
        staff_role_ids: list[int],
        month: int,
    ):

        stmt = (
            select(SchoolMonthPlanItem)
            .join(
                SchoolMonthPlanItemAssignee,
                SchoolMonthPlanItemAssignee.month_item_id == SchoolMonthPlanItem.id,
            )
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id == SchoolMonthPlanItem.month_plan_id,
            )
            .join(
                SchoolPlan,
                SchoolPlan.id == SchoolMonthPlan.school_plan_id,
            )
            .where(
                SchoolPlan.school_id == school_id,
                SchoolMonthPlan.month == month,
                SchoolMonthPlanItemAssignee.staff_role_id.in_(staff_role_ids),
                SchoolMonthPlanItem.is_included.is_(True),
            )
            .order_by(
                SchoolMonthPlanItem.week_of_month.asc(),
                SchoolMonthPlanItem.planned_start.asc(),
            )
        )

        res = await db.execute(stmt)
        return res.scalars().unique().all()
