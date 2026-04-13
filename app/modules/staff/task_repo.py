from typing import cast

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.planning.enums import PlanItemStatus
from app.modules.planning.models_month_plan import (
    SchoolMonthPlanItem,
    SchoolMonthPlan,
)
from app.modules.planning.models_month_plan import SchoolMonthPlanItemAssignee, SchoolMonthPlanItemExecution
from app.modules.planning.models_school import SchoolPlan


class StaffTasksRepo:

    @staticmethod
    async def list_tasks_for_staff(
            db: AsyncSession,
            *,
            school_id: int,
            staff_role_ids: list[int],
            month: int,
            statuses: list[PlanItemStatus] | None = None,
    ) -> list[SchoolMonthPlanItem]:
        stmt = (
            select(SchoolMonthPlanItem)
            .options(
                # источник задачи
                selectinload(SchoolMonthPlanItem.source_row11),

                # исполнение задачи
                selectinload(SchoolMonthPlanItem.execution),

                # места рассмотрения уже у month item
                selectinload(SchoolMonthPlanItem.review_places),
            )
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
        )

        if statuses:
            stmt = stmt.where(SchoolMonthPlanItem.status.in_(statuses))

        status_order = case(
            (SchoolMonthPlanItem.status == PlanItemStatus.TODO, 1),
            (SchoolMonthPlanItem.status == PlanItemStatus.IN_PROGRESS, 2),
            (SchoolMonthPlanItem.status == PlanItemStatus.DONE, 3),
            (SchoolMonthPlanItem.status == PlanItemStatus.NOT_EXECUTED, 4),
            else_=99,
        )

        stmt = stmt.order_by(
            SchoolMonthPlanItem.week_of_month.asc().nulls_last(),
            SchoolMonthPlanItem.planned_start.asc().nulls_last(),
            status_order.asc(),
            SchoolMonthPlanItem.id.asc(),
        )

        result = await db.scalars(stmt)
        return cast(list[SchoolMonthPlanItem], result.unique().all())

    # ---------------------------
    # 🔹 Получить задачу с проверкой доступа
    # ---------------------------
    @staticmethod
    async def get_staff_task_by_id(
            db: AsyncSession,
            *,
            month_item_id: int,
            school_id: int,
            staff_role_ids: list[int],
    ) -> SchoolMonthPlanItem | None:
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
                SchoolMonthPlanItem.id == month_item_id,
                SchoolPlan.school_id == school_id,
                SchoolMonthPlanItemAssignee.staff_role_id.in_(staff_role_ids),
                SchoolMonthPlanItem.is_included.is_(True),
            )
        )

        result = await db.scalars(stmt)
        return cast(SchoolMonthPlanItem | None, result.unique().first())


class SchoolMonthPlanItemExecutionRepo:

    # ---------------------------
    # 🔹 получить по задаче
    # ---------------------------
    @staticmethod
    async def get_by_item_id(
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> SchoolMonthPlanItemExecution | None:
        stmt = select(SchoolMonthPlanItemExecution).where(
            SchoolMonthPlanItemExecution.month_item_id == month_item_id
        )

        result = await db.scalars(stmt)
        return result.first()

    # ---------------------------
    # 🔹 получить или создать
    # ---------------------------
    @staticmethod
    async def get_or_create(
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int | None,
    ) -> SchoolMonthPlanItemExecution:
        obj = await SchoolMonthPlanItemExecutionRepo.get_by_item_id(
            db,
            month_item_id=month_item_id,
        )

        if obj:
            return obj

        obj = SchoolMonthPlanItemExecution(
            month_item_id=month_item_id,
            created_by_user_id=user_id,
        )

        db.add(obj)
        await db.flush()

        return obj

    # ---------------------------
    # 🔹 обновление
    # ---------------------------
    @staticmethod
    async def update(
            db: AsyncSession,
            *,
            obj: SchoolMonthPlanItemExecution,
            data: dict,
            user_id: int | None,
    ) -> SchoolMonthPlanItemExecution:

        for field, value in data.items():
            if hasattr(obj, field):
                setattr(obj, field, value)

        obj.updated_by_user_id = user_id

        await db.flush()
        return obj

    # ---------------------------
    # 🔹 удалить (опционально)
    # ---------------------------
    @staticmethod
    async def delete(
            db: AsyncSession,
            *,
            obj: SchoolMonthPlanItemExecution,
    ) -> None:
        await db.delete(obj)
