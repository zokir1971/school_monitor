from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.planning.enums import PlanStatus, PlanItemStatus, AssignmentKind
# твои модели/enum/dto
from app.modules.planning.models_month_plan import SchoolMonthPlan, SchoolMonthPlanItem, \
    SchoolMonthPlanItemReviewPlace, \
    SchoolMonthPlanItemAssignee
from app.modules.planning.models_school import SchoolPlan, SchoolPlanRow11
from app.modules.planning.schemas.month_plan_inputs import MonthItemUpdate
from app.modules.planning.schemas.month_plan_page_schemas import MonthPlanAssignmentSummaryDTO
from app.modules.planning.utils.month_plan_utils import format_short_person_name
from app.modules.staff.models_staff_school import SchoolStaffMember, SchoolStaffRole


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

    @staticmethod
    async def archive_month_plans_by_school_plan(
            db: AsyncSession,
            *,
            school_plan_id: int,
    ) -> int:
        """
        Архивирует все месячные планы
        указанного годового плана.

        ВАЖНО:
        SchoolMonthPlanItem не изменяются.

        Их фактические статусы:
            TODO
            IN_PROGRESS
            DONE
            REVIEWED
            NOT_EXECUTED

        должны сохраниться для истории и статистики.

        Repository не выполняет commit / rollback.
        """

        result = await db.execute(
            update(SchoolMonthPlan)
            .where(
                SchoolMonthPlan.school_plan_id
                == school_plan_id,

                SchoolMonthPlan.status
                != PlanStatus.ARCHIVED,
            )
            .values(
                status=PlanStatus.ARCHIVED,
            )
        )

        return int(result.rowcount or 0)

    # -----------------------------------------------------
    # Items (school_month_plan_items)
    # -----------------------------------------------------
    @staticmethod
    async def list_items(
            db: AsyncSession, *, month_plan_id: int, with_source: bool = False, refresh: bool = False
    ) -> list[SchoolMonthPlanItem]:

        stmt = (
            select(SchoolMonthPlanItem)
            .where(SchoolMonthPlanItem.month_plan_id == month_plan_id)
            .order_by(SchoolMonthPlanItem.id.asc())
            .options(
                selectinload(SchoolMonthPlanItem.review_places),
            )
        )

        if with_source:
            stmt = stmt.options(
                selectinload(SchoolMonthPlanItem.source_row11)
                .selectinload(SchoolPlanRow11.direction),

                selectinload(SchoolMonthPlanItem.source_row11)
                .selectinload(SchoolPlanRow11.role_assignments),
            )

        if refresh:
            stmt = stmt.execution_options(populate_existing=True)
        res = await db.execute(stmt)
        return list(res.scalars().unique().all())

    @staticmethod
    async def get_assignment_summaries_by_month_plan(
            db: AsyncSession,
            *,
            month_plan_id: int,
    ) -> dict[int, MonthPlanAssignmentSummaryDTO]:
        """
        Получить краткую сводку назначений всех задач
        месячного плана одним пакетным SQL-запросом.

        Возвращает:

            {
                month_item_id: MonthPlanAssignmentSummaryDTO(
                    has_primary_assignee=True,
                    primary_assignee_name="ТУРСУНБАЕВА Т.Б.",
                    co_executor_count=2,
                    co_executor_names=[
                        "ИВАНОВА А.С.",
                        "ПЕТРОВ Б.К.",
                    ],
                )
            }

        ORM-объекты назначений, должностей и сотрудников
        наружу не передаются.
        """

        stmt = (
            select(
                SchoolMonthPlanItemAssignee.month_item_id.label(
                    "month_item_id"
                ),
                SchoolMonthPlanItemAssignee.assignment_kind.label(
                    "assignment_kind"
                ),
                SchoolStaffMember.full_name.label(
                    "full_name"
                ),
            )
            .join(
                SchoolMonthPlanItem,
                SchoolMonthPlanItem.id
                == SchoolMonthPlanItemAssignee.month_item_id,
            )
            .join(
                SchoolStaffRole,
                SchoolStaffRole.id
                == SchoolMonthPlanItemAssignee.staff_role_id,
            )
            .join(
                SchoolStaffMember,
                SchoolStaffMember.id
                == SchoolStaffRole.staff_member_id,
            )
            .where(
                SchoolMonthPlanItem.month_plan_id
                == month_plan_id
            )
            .order_by(
                SchoolMonthPlanItemAssignee.month_item_id,
                SchoolMonthPlanItemAssignee.assignment_kind,
                SchoolStaffMember.full_name,
            )
        )

        rows = (
            await db.execute(stmt)
        ).all()

        summaries: dict[
            int,
            MonthPlanAssignmentSummaryDTO,
        ] = {}

        for row in rows:
            month_item_id = int(row.month_item_id)

            summary = summaries.get(month_item_id)

            if summary is None:
                summary = MonthPlanAssignmentSummaryDTO(
                    has_primary_assignee=False,
                    primary_assignee_name=None,
                    co_executor_count=0,
                )
                summaries[month_item_id] = summary

            assignment_kind = (
                row.assignment_kind.value
                if hasattr(row.assignment_kind, "value")
                else row.assignment_kind
            )

            short_name = format_short_person_name(
                row.full_name
            )

            if assignment_kind == AssignmentKind.PRIMARY.value:
                summary.has_primary_assignee = True
                summary.primary_assignee_name = short_name
                continue

            if (
                    assignment_kind
                    == AssignmentKind.CO_EXECUTOR.value
            ):
                if short_name not in summary.co_executor_names:
                    summary.co_executor_names.append(
                        short_name
                    )

        for summary in summaries.values():
            summary.co_executor_count = len(
                summary.co_executor_names
            )

        return summaries

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

    @staticmethod
    def _previous_months_in_quarter(month: int) -> list[int]:
        if month in (9, 10):
            quarter_months = [9, 10]
        elif month in (11, 12):
            quarter_months = [11, 12]
        elif month in (1, 2, 3):
            quarter_months = [1, 2, 3]
        elif month in (4, 5):
            quarter_months = [4, 5]
        else:
            return []

        result: list[int] = []
        for m in quarter_months:
            if m == month:
                break
            result.append(m)
        return result

    @staticmethod
    async def list_previously_included_quarter_source_ids(
            db: AsyncSession,
            *,
            school_plan_id: int,
            source_row11_ids: list[int],
            previous_months: list[int],
    ) -> set[int]:
        if not source_row11_ids or not previous_months:
            return set()

        stmt = (
            select(SchoolMonthPlanItem.source_row11_id)
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )
            .where(
                SchoolMonthPlan.school_plan_id == school_plan_id,
                SchoolMonthPlan.month.in_(previous_months),
                SchoolMonthPlanItem.source_row11_id.in_(
                    source_row11_ids
                ),
                SchoolMonthPlanItem.is_included.is_(True),
            )
            .distinct()
        )

        source_ids = (
            await db.scalars(stmt)
        ).all()

        return {
            source_id
            for source_id in source_ids
            if source_id is not None
        }

    @staticmethod
    async def quarterly_already_included_before_current_month(
            db: AsyncSession,
            *,
            school_plan_id: int,
            source_row11_id: int,
            target_month: int,
    ) -> bool:
        """
        Совместимый wrapper для старых вызовов.
        """

        previous_months = (
            SchoolMonthlyPlanRepo
            ._previous_months_in_quarter(target_month)
        )

        if not previous_months:
            return False

        existing_ids = (
            await SchoolMonthlyPlanRepo
            .list_previously_included_quarter_source_ids(
                db,
                school_plan_id=school_plan_id,
                source_row11_ids=[source_row11_id],
                previous_months=previous_months,
            )
        )

        return source_row11_id in existing_ids


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
