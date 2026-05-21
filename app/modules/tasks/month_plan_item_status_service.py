from __future__ import annotations

from datetime import date

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.models_month_plan import SchoolMonthPlanItem
from app.modules.planning.enums import PlanItemStatus


class SchoolMonthPlanItemStatusService:
    @staticmethod
    async def auto_mark_expired_as_not_executed(db: AsyncSession) -> int:
        today = date.today()

        stmt = (
            update(SchoolMonthPlanItem)
            .where(
                SchoolMonthPlanItem.planned_end.is_not(None),
                SchoolMonthPlanItem.planned_end < today,
                SchoolMonthPlanItem.status.in_(
                    [
                        PlanItemStatus.TODO,
                        PlanItemStatus.IN_PROGRESS,
                    ]
                ),
            )
            .values(
                status=PlanItemStatus.NOT_EXECUTED,
            )
        )

        result = await db.execute(stmt)
        await db.commit()

        return result.rowcount or 0
