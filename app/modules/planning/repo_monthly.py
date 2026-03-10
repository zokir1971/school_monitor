from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.planning.enums import PlanStatus, PlanItemStatus
# твои модели/enum/dto
from app.modules.planning.models_month_plan import SchoolMonthPlan, SchoolMonthPlanItem, SchoolMonthPlanItemReviewPlace
from app.modules.planning.models_school import SchoolPlan, SchoolPlanRow11
from app.modules.planning.schemas import MonthItemUpdate
from app.modules.planning.utils.month_plan_utils import month_to_quarter

ACADEMIC_MONTHS = {9, 10, 11, 12, 1, 2, 3, 4, 5}

QUARTERS = {
    1: (9, 10, 11),
    2: (12, 1, 2),
    3: (3, 4, 5),
    4: (6, 7, 8),
}


class SchoolMonthlyPlanRepo:
    # -----------------------------------------------------
    # Month plan (school_month_plans)
    # -----------------------------------------------------
    @staticmethod
    async def get_month_plan(
            db: AsyncSession, *, school_plan_id: int, year: int, month: int
    ) -> SchoolMonthPlan | None:
        res = await db.execute(
            select(SchoolMonthPlan).where(
                SchoolMonthPlan.school_plan_id == school_plan_id,
                SchoolMonthPlan.year == year,
                SchoolMonthPlan.month == month,
            )
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def get_month_plan_by_id(db: AsyncSession, *, month_plan_id: int) -> SchoolMonthPlan | None:
        res = await db.execute(select(SchoolMonthPlan).where(SchoolMonthPlan.id == month_plan_id))
        return res.scalar_one_or_none()

    @staticmethod
    async def create_month_plan(
            db: AsyncSession, *, school_plan_id: int, year: int, month: int
    ) -> SchoolMonthPlan:
        mp = SchoolMonthPlan(
            school_plan_id=school_plan_id,
            year=year,
            month=month,
        )
        db.add(mp)
        await db.flush()  # чтобы mp.id появился сразу
        return mp

    @staticmethod
    async def get_or_create_month_plan(
            db: AsyncSession, *, school_plan_id: int, year: int, month: int
    ) -> tuple[SchoolMonthPlan, bool]:
        mp = await SchoolMonthlyPlanRepo.get_month_plan(
            db, school_plan_id=school_plan_id, year=year, month=month
        )
        if mp:
            return mp, False

        try:
            mp = await SchoolMonthlyPlanRepo.create_month_plan(
                db, school_plan_id=school_plan_id, year=year, month=month
            )
            return mp, True
        except IntegrityError:
            # На случай гонки: другой запрос успел создать тот же месяц
            await db.rollback()
            mp2 = await SchoolMonthlyPlanRepo.get_month_plan(
                db, school_plan_id=school_plan_id, year=year, month=month
            )
            if not mp2:
                raise
            return mp2, False

    @staticmethod
    async def set_month_plan_status(
            db: AsyncSession, *, month_plan_id: int, status: PlanStatus
    ) -> None:
        await db.execute(
            update(SchoolMonthPlan)
            .where(SchoolMonthPlan.id == month_plan_id)
            .values(status=status)
        )

    # -----------------------------------------------------
    # Items (school_month_plan_items)
    # -----------------------------------------------------
    @staticmethod
    async def list_items(
            db: AsyncSession, *, month_plan_id: int, with_source: bool = False
    ) -> list[SchoolMonthPlanItem]:

        stmt = (
            select(SchoolMonthPlanItem)
            .where(SchoolMonthPlanItem.month_plan_id == month_plan_id)
            .order_by(SchoolMonthPlanItem.id.asc())  # стабильная сортировка
        )

        if with_source:
            stmt = stmt.options(
                selectinload(SchoolMonthPlanItem.source_row11)
                .selectinload(SchoolPlanRow11.direction),

                selectinload(SchoolMonthPlanItem.source_row11)
                .selectinload(SchoolPlanRow11.role_assignments),
            )

        res = await db.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_item(
            db: AsyncSession, *, item_id: int, with_source: bool = False
    ) -> SchoolMonthPlanItem | None:
        stmt = select(SchoolMonthPlanItem).where(SchoolMonthPlanItem.id == item_id)

        if with_source:
            # В async обычно безопаснее и предсказуемее, чем joinedload на сложных графах
            stmt = stmt.options(selectinload(SchoolMonthPlanItem.source_row11))

        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def list_existing_source_row11_ids(
            db: AsyncSession, *, month_plan_id: int
    ) -> set[int]:
        """
        Нужен для safe-build (не падать на UniqueConstraint).
        """
        res = await db.execute(
            select(SchoolMonthPlanItem.source_row11_id).where(
                SchoolMonthPlanItem.month_plan_id == month_plan_id
            )
        )
        return set(res.scalars().all())

    @staticmethod
    async def delete_items(
            db: AsyncSession, *, month_plan_id: int
    ) -> None:
        """
        Если хочешь "пересобрать" план заново.
        """
        await db.execute(
            delete(SchoolMonthPlanItem).where(
                SchoolMonthPlanItem.month_plan_id == month_plan_id
            )
        )

    @staticmethod
    async def create_items_bulk(
            db: AsyncSession,
            *,
            month_plan_id: int,
            source_row11_ids: Sequence[int],
            default_included: bool = True,
            default_week: int | None = None,
            skip_existing: bool = True,
    ) -> list[SchoolMonthPlanItem]:
        """
        Создает записи SchoolMonthPlanItem для month_plan.

        Возвращает список СОЗДАННЫХ ORM-объектов, у которых после flush()
        уже доступны:
            - id
            - source_row11_id

        skip_existing=True:
            не создаёт записи для source_row11_id, которые уже существуют
            в рамках данного month_plan_id.
        """
        if not source_row11_ids:
            return []

        ids = list(dict.fromkeys(int(x) for x in source_row11_ids))  # unique + сохранить порядок

        if skip_existing:
            existing = await SchoolMonthlyPlanRepo.list_existing_source_row11_ids(
                db,
                month_plan_id=month_plan_id,
            )
            ids = [sid for sid in ids if sid not in existing]
            if not ids:
                return []

        items = [
            SchoolMonthPlanItem(
                month_plan_id=month_plan_id,
                source_row11_id=sid,
                is_included=default_included,
                week_of_month=default_week,
                status=PlanItemStatus.TODO,
            )
            for sid in ids
        ]

        db.add_all(items)
        await db.flush()  # после этого у items уже есть item.id

        return items

    @staticmethod
    async def upsert_item_flags_bulk(
            db: AsyncSession, *, updates: Sequence[MonthItemUpdate]
    ) -> None:
        """
        Массово обновляет:
        is_included / week_of_month / planned_start / planned_end / notes
        по item_id.
        """
        if not updates:
            return

        for u in updates:
            await db.execute(
                update(SchoolMonthPlanItem)
                .where(SchoolMonthPlanItem.id == u.item_id)
                .values(
                    is_included=u.is_included,
                    week_of_month=u.week_of_month,
                    planned_start=u.planned_start,
                    planned_end=u.planned_end,
                    notes=u.notes,
                )
            )

    @staticmethod
    async def set_item_status(
            db: AsyncSession, *, item_id: int, status: PlanItemStatus
    ) -> None:
        await db.execute(
            update(SchoolMonthPlanItem)
            .where(SchoolMonthPlanItem.id == item_id)
            .values(status=status)
        )

    # удаление месячного плана
    @staticmethod
    async def get_month_plan_for_school_by_id(
            db: AsyncSession,
            *,
            month_plan_id: int,
            school_id: int,
    ) -> SchoolMonthPlan | None:

        res = await db.execute(
            select(SchoolMonthPlan)
            .join(SchoolPlan, SchoolPlan.id == SchoolMonthPlan.school_plan_id)
            .where(
                SchoolMonthPlan.id == month_plan_id,
                SchoolPlan.school_id == school_id,
            )
        )

        return res.scalar_one_or_none()

    @staticmethod
    async def delete_month_plan(
            db: AsyncSession,
            *,
            month_plan: SchoolMonthPlan,
    ):
        await db.delete(month_plan)

    # -----------------------------------------------------
    # Source year plan rows (school_plan_rows_11)
    # -----------------------------------------------------
    @staticmethod
    async def list_source_rows11_for_school_plan(
            db: AsyncSession,
            *,
            school_plan_id: int,
    ) -> list[SchoolPlanRow11]:
        res = await db.execute(
            select(SchoolPlanRow11)
            .where(SchoolPlanRow11.school_plan_id == school_plan_id)
            .options(
                selectinload(SchoolPlanRow11.review_places),
                selectinload(SchoolPlanRow11.required_documents),
            )
            .order_by(
                SchoolPlanRow11.row_order.asc(),
                SchoolPlanRow11.id.asc(),
            )
        )

        return list(res.scalars().unique().all())

    # -----------------------------------------------------
    # QUARTER checks
    # -----------------------------------------------------
    @staticmethod
    async def quarterly_already_planned_in_quarter(
            db: AsyncSession,
            *,
            school_plan_id: int,
            source_row11_id: int,
            target_month: int,
            only_active: bool = False,
    ) -> bool:
        q = month_to_quarter(target_month)

        months = QUARTERS[q]

        stmt = (
            select(SchoolMonthPlanItem.id)
            .join(SchoolMonthPlan, SchoolMonthPlan.id == SchoolMonthPlanItem.month_plan_id)
            .where(
                SchoolMonthPlan.school_plan_id == school_plan_id,
                SchoolMonthPlan.month.in_(months),
                SchoolMonthPlanItem.source_row11_id == source_row11_id,
                SchoolMonthPlanItem.is_included.is_(True),
            )
        )
        if only_active:
            stmt = stmt.where(SchoolMonthPlan.status == PlanStatus.ACTIVE)

        res = await db.execute(stmt.limit(1))
        return res.scalar_one_or_none() is not None

    # -----------------------------------------------------
    # SchoolPlan fetch helpers
    # -----------------------------------------------------
    @staticmethod
    async def get_school_plan(
            db: AsyncSession, *, school_plan_id: int
    ) -> SchoolPlan | None:
        res = await db.execute(select(SchoolPlan).where(SchoolPlan.id == school_plan_id))
        return res.scalar_one_or_none()

    @staticmethod
    async def get_active_school_plan(
            db: AsyncSession, *, school_id: int
    ) -> SchoolPlan | None:
        res = await db.execute(
            select(SchoolPlan)
            .where(SchoolPlan.school_id == school_id, SchoolPlan.status == PlanStatus.ACTIVE)
            .limit(1)
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def get_school_plan_for_school(
            db: AsyncSession, *, school_plan_id: int, school_id: int
    ) -> SchoolPlan | None:
        res = await db.execute(
            select(SchoolPlan).where(SchoolPlan.id == school_plan_id, SchoolPlan.school_id == school_id)
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def count_items(db: AsyncSession, *, month_plan_id: int) -> int:
        res = await db.execute(
            select(func.count(SchoolMonthPlanItem.id)).where(
                SchoolMonthPlanItem.month_plan_id == month_plan_id
            )
        )
        return int(res.scalar() or 0)


class SchoolMonthPlanItemRepo:
    @staticmethod
    async def get_item(db: AsyncSession, *, item_id: int) -> SchoolMonthPlanItem | None:
        res = await db.execute(select(SchoolMonthPlanItem).where(SchoolMonthPlanItem.id == item_id))
        return res.scalar_one_or_none()

    @staticmethod
    async def list_items_by_ids(
            db: AsyncSession, *, month_plan_id: int, item_ids: list[int]
    ) -> list[SchoolMonthPlanItem]:
        if not item_ids:
            return []
        res = await db.execute(
            select(SchoolMonthPlanItem).where(
                SchoolMonthPlanItem.month_plan_id == month_plan_id,
                SchoolMonthPlanItem.id.in_(item_ids),
            )
        )
        return list(res.scalars().all())

    @staticmethod
    async def create_month_item_review_places_bulk(
            db: AsyncSession,
            *,
            rows: list[dict],
    ) -> None:
        """
        Bulk вставка мест рассмотрения для month items.
        """
        if not rows:
            return

        await db.execute(
            sa.insert(SchoolMonthPlanItemReviewPlace),
            rows,
        )
