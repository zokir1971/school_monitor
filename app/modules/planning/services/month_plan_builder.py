# app/modules/planning/services/month_plan_builder.py

from __future__ import annotations

import re
from app.modules.planning.repositories.review_place_sync_repo import ReviewPlaceSyncRepo

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.constants import ACADEMIC_MONTHS
from app.modules.planning.enums import PlanPeriodType
from app.modules.planning.models_month_plan import SchoolMonthPlanItem
from app.modules.planning.models_school import SchoolPlanRow11
from app.modules.planning.repositories.month_plan_repository import (
    SchoolMonthPlanItemRepo,
    SchoolMonthlyPlanRepo,
)
from app.modules.planning.utils.month_plan_utils import quarter_of_month, previous_months_in_quarter


class MonthPlanBuilder:
    """Формирует строки месячного плана из строк годового плана."""

    @classmethod
    async def build_items(
        cls,
        db: AsyncSession,
        *,
        school_plan_id: int,
        month_plan_id: int,
        month: int,
    ) -> None:
        if month not in ACADEMIC_MONTHS:
            raise ValueError(
                f"Недопустимый месяц учебного года: {month}"
            )

        locked_plan = await ReviewPlaceSyncRepo.lock_plan(db, school_plan_id=school_plan_id)
        if not locked_plan or str(getattr(locked_plan["status"], "value", locked_plan["status"])) == "archived":
            raise ValueError("Нельзя создавать задачи архивного годового плана")

        rows = await SchoolMonthlyPlanRepo.list_source_rows11_for_school_plan(
            db,
            school_plan_id=school_plan_id,
        )

        target_quarter = quarter_of_month(month)

        month_ids: list[int] = []
        months_ids: list[int] = []
        monthly_ids: list[int] = []
        all_year_ids: list[int] = []
        quarter_candidate_ids: list[int] = []
        row_map: dict[int, SchoolPlanRow11] = {}

        for row in rows:
            row_map[row.id] = row
            period_type_value = cls._enum_value(
                row.period_type
            )

            if period_type_value == PlanPeriodType.MONTH.value:
                if cls._to_int(row.period_value_int) == month:
                    month_ids.append(row.id)
                continue

            if period_type_value == PlanPeriodType.MONTHS.value:
                if month in cls.parse_month_values(
                        row.period_values
                ):
                    months_ids.append(row.id)
                continue

            if period_type_value == PlanPeriodType.MONTHLY.value:
                monthly_ids.append(row.id)
                continue

            if period_type_value == PlanPeriodType.ALL_YEAR.value:
                all_year_ids.append(row.id)
                continue

            if period_type_value != PlanPeriodType.QUARTER.value:
                continue

            if target_quarter is None:
                continue

            allowed_quarters = cls.parse_int_set(
                row.period_value_int
            )

            if (
                    allowed_quarters
                    and target_quarter not in allowed_quarters
            ):
                continue

            quarter_candidate_ids.append(row.id)

        previous_quarter_months = previous_months_in_quarter(
            month
        )

        already_included_quarter_ids = (
            await SchoolMonthlyPlanRepo
            .list_previously_included_quarter_source_ids(
                db,
                school_plan_id=school_plan_id,
                source_row11_ids=quarter_candidate_ids,
                previous_months=previous_quarter_months,
            )
        )

        quarter_ids = [
            row_id
            for row_id in quarter_candidate_ids
            if row_id not in already_included_quarter_ids
        ]

        created_items: list[SchoolMonthPlanItem] = []
        non_quarter_ids = (
            month_ids
            + months_ids
            + monthly_ids
            + all_year_ids
        )

        if non_quarter_ids:
            created_items.extend(
                await SchoolMonthlyPlanRepo.create_items_bulk(
                    db,
                    month_plan_id=month_plan_id,
                    source_row11_ids=non_quarter_ids,
                    default_included=True,
                    default_week=None,
                )
            )

        if quarter_ids:
            created_items.extend(
                await SchoolMonthlyPlanRepo.create_items_bulk(
                    db,
                    month_plan_id=month_plan_id,
                    source_row11_ids=quarter_ids,
                    default_included=False,
                    default_week=None,
                )
            )

        review_place_rows = cls._build_review_place_rows(
            created_items=created_items,
            row_map=row_map,
        )

        if review_place_rows:
            await SchoolMonthPlanItemRepo.create_month_item_review_places_bulk(
                db,
                rows=review_place_rows,
            )

        await ReviewPlaceSyncRepo.sync(db, school_plan_id=school_plan_id, month_plan_id=month_plan_id, locked=True)

        await db.flush()

    @staticmethod
    def quarter_of_month(month: int) -> int | None:
        if month in (9, 10):
            return 1
        if month in (11, 12):
            return 2
        if month in (1, 2, 3):
            return 3
        if month in (4, 5):
            return 4
        return None

    @staticmethod
    def quarter_months(month: int) -> tuple[int, ...]:
        if month in (9, 10):
            return 9, 10
        if month in (11, 12):
            return 11, 12
        if month in (1, 2, 3):
            return 1, 2, 3
        if month in (4, 5):
            return 4, 5
        return ()

    @classmethod
    def previous_months_in_quarter(cls, month: int) -> tuple[int, ...]:
        result: list[int] = []
        for current_month in cls.quarter_months(month):
            if current_month == month:
                break
            result.append(current_month)
        return tuple(result)

    @staticmethod
    def parse_int_set(value) -> set[int]:
        if value is None:
            return set()
        if isinstance(value, int):
            return {value}
        if isinstance(value, str):
            return {int(item) for item in re.findall(r"\d+", value)}
        try:
            return {int(value)}
        except (TypeError, ValueError):
            return set()

    @staticmethod
    def parse_month_values(value: str | None) -> set[int]:
        if not value:
            return set()
        return {
            int(item)
            for item in re.findall(r"\d+", str(value))
            if 1 <= int(item) <= 12
        }

    @staticmethod
    def _to_int(value) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _enum_value(value) -> str:
        return str(getattr(value, "value", value))

    @staticmethod
    def _build_review_place_rows(
        *,
        created_items: list[SchoolMonthPlanItem],
        row_map: dict[int, SchoolPlanRow11],
    ) -> list[dict]:
        result: list[dict] = []

        for item in created_items:
            source_row = row_map.get(item.source_row11_id)
            if source_row is None:
                continue

            for relation in source_row.review_places or []:
                review_place = getattr(relation, "review_place", None)
                if review_place is None:
                    continue

                result.append(
                    {
                        "month_item_id": item.id,
                        "review_place": getattr(
                            review_place,
                            "value",
                            review_place,
                        ),
                    }
                )

        return result
