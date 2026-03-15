# app/modules/planning/service/school_statistics_service.py

from __future__ import annotations

from dataclasses import dataclass, asdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import PlanPeriodType, ReviewPlace
from app.modules.planning.models import PlanDirection
from app.modules.planning.models_school import SchoolPlanRow11, SchoolPlan, SchoolPlanRow11ReviewPlace
from app.modules.planning.utils.school_statistics_utils import (
    ACADEMIC_MONTHS_COUNT,
    QUARTERS_COUNT,
)


@dataclass
class DirectionPeriodStatDTO:
    direction_id: int
    direction_name: str
    month_count: int = 0
    months_count: int = 0
    monthly_count: int = 0
    quarter_count: int = 0
    all_year_count: int = 0


@dataclass
class DirectionPlannedStatDTO:
    direction_id: int
    direction_name: str
    planned_count: int


@dataclass
class DirectionReviewPlaceStatDTO:
    direction_id: int
    direction_name: str

    ped_council_count: int = 0
    method_council_count: int = 0
    director_council_count: int = 0
    administrative_council_count: int = 0
    method_assoc_count: int = 0

    total_review_places_count: int = 0


@dataclass
class ReviewPlaceTotalsDTO:
    ped_council_count: int = 0
    method_council_count: int = 0
    director_council_count: int = 0
    administrative_council_count: int = 0
    method_assoc_count: int = 0

    total_review_places_count: int = 0


class SchoolPlanStatisticsService:
    @classmethod
    async def _get_direction_map(cls, db: AsyncSession) -> dict[int, str]:
        result = await db.execute(
            select(
                PlanDirection.id,
                PlanDirection.full_title,
            ).order_by(PlanDirection.id)
        )

        rows = result.all()

        return {
            row.id: row.full_title
            for row in rows
        }

    @staticmethod
    def _parse_int_list(value: str | None) -> list[int]:
        if not value:
            return []

        result: list[int] = []
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue

            try:
                num = int(part)
            except ValueError:
                continue

            result.append(num)

        return result

    @classmethod
    def _normalize_month_values(cls, value: str | None) -> list[int]:
        values = cls._parse_int_list(value)
        values = [x for x in values if 1 <= x <= 12]
        return sorted(set(values))

    @classmethod
    def _get_row_planned_count(cls, row) -> int:
        period_type = row.period_type
        period_value_int = row.period_value_int
        period_values = row.period_values

        if period_type == PlanPeriodType.MONTH:
            return 1 if period_value_int is not None else 0

        if period_type == PlanPeriodType.MONTHS:
            return len(cls._normalize_month_values(period_values))

        if period_type == PlanPeriodType.MONTHLY:
            return ACADEMIC_MONTHS_COUNT

        if period_type == PlanPeriodType.QUARTER:
            return QUARTERS_COUNT

        if period_type == PlanPeriodType.ALL_YEAR:
            return ACADEMIC_MONTHS_COUNT

        return 0

    @staticmethod
    async def get_active_school_plan(db: AsyncSession, school_id: int):
        result = await db.execute(
            select(SchoolPlan)
            .where(SchoolPlan.school_id == school_id)
            .order_by(SchoolPlan.id.desc())
        )
        return result.scalars().first()

    @classmethod
    async def get_period_statistics_by_direction(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
    ) -> list[DirectionPeriodStatDTO]:
        direction_map = await cls._get_direction_map(db)

        result = await db.execute(
            select(
                SchoolPlanRow11.direction_id,
                SchoolPlanRow11.row_order,
                SchoolPlanRow11.period_type,
                SchoolPlanRow11.period_value_int,
                SchoolPlanRow11.period_values,
            )
            .where(SchoolPlanRow11.school_plan_id == school_plan_id)
            .order_by(SchoolPlanRow11.direction_id, SchoolPlanRow11.row_order)
        )

        rows = result.all()

        stats_map: dict[int, DirectionPeriodStatDTO] = {
            direction_id: DirectionPeriodStatDTO(
                direction_id=direction_id,
                direction_name=direction_name,
            )
            for direction_id, direction_name in direction_map.items()
        }

        for row in rows:
            direction_id = row.direction_id
            if direction_id is None:
                continue

            if direction_id not in stats_map:
                stats_map[direction_id] = DirectionPeriodStatDTO(
                    direction_id=direction_id,
                    direction_name=f"Направление {direction_id}",
                )

            item = stats_map[direction_id]

            if row.period_type == PlanPeriodType.MONTH:
                item.month_count += 1
            elif row.period_type == PlanPeriodType.MONTHS:
                item.months_count += 1
            elif row.period_type == PlanPeriodType.MONTHLY:
                item.monthly_count += 1
            elif row.period_type == PlanPeriodType.QUARTER:
                item.quarter_count += 1
            elif row.period_type == PlanPeriodType.ALL_YEAR:
                item.all_year_count += 1

        return [stats_map[direction_id] for direction_id in direction_map]

    @classmethod
    async def get_planned_statistics_by_direction(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
    ) -> list[DirectionPlannedStatDTO]:
        direction_map = await cls._get_direction_map(db)

        result = await db.execute(
            select(
                SchoolPlanRow11.direction_id,
                SchoolPlanRow11.row_order,
                SchoolPlanRow11.period_type,
                SchoolPlanRow11.period_value_int,
                SchoolPlanRow11.period_values,
            )
            .where(SchoolPlanRow11.school_plan_id == school_plan_id)
            .order_by(SchoolPlanRow11.direction_id, SchoolPlanRow11.row_order)
        )

        rows = result.all()

        stats_map: dict[int, int] = {
            direction_id: 0 for direction_id in direction_map
        }

        for row in rows:
            direction_id = row.direction_id
            if direction_id is None:
                continue

            if direction_id not in stats_map:
                stats_map[direction_id] = 0

            stats_map[direction_id] += cls._get_row_planned_count(row)

        return [
            DirectionPlannedStatDTO(
                direction_id=direction_id,
                direction_name=direction_map.get(direction_id, f"Направление {direction_id}"),
                planned_count=stats_map.get(direction_id, 0),
            )
            for direction_id in direction_map
        ]

    @classmethod
    async def get_review_place_statistics_by_direction(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
    ) -> list[DirectionReviewPlaceStatDTO]:
        direction_map = await cls._get_direction_map(db)

        result = await db.execute(
            select(
                SchoolPlanRow11.direction_id,
                SchoolPlanRow11.row_order,
                SchoolPlanRow11ReviewPlace.review_place,
            )
            .join(
                SchoolPlanRow11ReviewPlace,
                SchoolPlanRow11ReviewPlace.row11_id == SchoolPlanRow11.id,
            )
            .where(SchoolPlanRow11.school_plan_id == school_plan_id)
            .order_by(SchoolPlanRow11.direction_id, SchoolPlanRow11.row_order)
        )

        rows = result.all()

        stats_map: dict[int, DirectionReviewPlaceStatDTO] = {
            direction_id: DirectionReviewPlaceStatDTO(
                direction_id=direction_id,
                direction_name=direction_name,
            )
            for direction_id, direction_name in direction_map.items()
        }

        for row in rows:
            direction_id = row.direction_id
            if direction_id is None:
                continue

            if direction_id not in stats_map:
                stats_map[direction_id] = DirectionReviewPlaceStatDTO(
                    direction_id=direction_id,
                    direction_name=f"Направление {direction_id}",
                )

            item = stats_map[direction_id]

            if row.review_place == ReviewPlace.PED_COUNCIL:
                item.ped_council_count += 1
            elif row.review_place == ReviewPlace.METHOD_COUNCIL:
                item.method_council_count += 1
            elif row.review_place == ReviewPlace.DIRECTOR_COUNCIL:
                item.director_council_count += 1
            elif row.review_place == ReviewPlace.ADMINISTRATIVE_COUNCIL:
                item.administrative_council_count += 1
            elif row.review_place == ReviewPlace.METHOD_ASSOC:
                item.method_assoc_count += 1

            item.total_review_places_count += 1

        return [stats_map[direction_id] for direction_id in direction_map]

    @classmethod
    async def get_statistics_page_data(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
    ) -> dict:
        period_stats = await cls.get_period_statistics_by_direction(
            db,
            school_plan_id=school_plan_id,
        )

        planned_stats = await cls.get_planned_statistics_by_direction(
            db,
            school_plan_id=school_plan_id,
        )

        review_place_stats = await cls.get_review_place_statistics_by_direction(
            db,
            school_plan_id=school_plan_id,
        )

        totals = ReviewPlaceTotalsDTO()

        for row in review_place_stats:
            totals.ped_council_count += row.ped_council_count
            totals.method_council_count += row.method_council_count
            totals.director_council_count += row.director_council_count
            totals.administrative_council_count += row.administrative_council_count
            totals.method_assoc_count += row.method_assoc_count

        totals.total_review_places_count = (
                totals.ped_council_count
                + totals.method_council_count
                + totals.director_council_count
                + totals.administrative_council_count
                + totals.method_assoc_count
        )

        total_planned_count = sum(x.planned_count for x in planned_stats)

        return {
            "period_stats": period_stats,
            "planned_stats": planned_stats,
            "review_place_stats": review_place_stats,
            "review_place_totals": asdict(totals),
            "total_planned_count": total_planned_count,
            "total_review_places_count": totals.total_review_places_count,  # ← добавить
        }
