# app/modules/statistics/school_statistics_service.py

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.constants import MONTH_LABELS
from app.modules.planning.enums import PlanPeriodType, ReviewPlace
from app.modules.planning.models_school import SchoolPlan
from app.modules.statistics.school_statistic_dto import (
    AnnualDirectionExecutionStatDTO,
    DirectionPeriodStatDTO,
    DirectionPlannedStatDTO,
    DirectionReviewPlaceStatDTO,
    MonthDirectionExecutionStatDTO,
    MonthlyExecutionStatDTO,
    ReviewPlaceTotalsDTO,
    StaffMonthDirectionStatDTO,
    StaffMonthlyExecutionStatDTO,
)
from app.modules.statistics.school_statistic_repo import (
    SchoolPlanStatisticsRepository,
    SchoolStatisticsRepository,
    StaffStatisticsRepository,
)
from app.modules.statistics.school_statistics_utils import (
    ACADEMIC_MONTHS_COUNT,
    QUARTERS_COUNT,
)


class SchoolPlanStatisticsService:
    """Бизнес-логика статистики годового плана школы."""

    repository = SchoolPlanStatisticsRepository

    @classmethod
    async def get_active_school_plan(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
    ) -> SchoolPlan | None:
        return await cls.repository.get_active_school_plan(
            db,
            school_id=school_id,
        )

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
                result.append(int(part))
            except ValueError:
                continue

        return result

    @classmethod
    def _normalize_month_values(cls, value: str | None) -> list[int]:
        values = cls._parse_int_list(value)
        return sorted({value for value in values if 1 <= value <= 12})

    @classmethod
    def _get_row_planned_count(cls, row: Any) -> int:
        if row.period_type == PlanPeriodType.MONTH:
            return 1 if row.period_value_int is not None else 0

        if row.period_type == PlanPeriodType.MONTHS:
            return len(cls._normalize_month_values(row.period_values))

        if row.period_type == PlanPeriodType.MONTHLY:
            return ACADEMIC_MONTHS_COUNT

        if row.period_type == PlanPeriodType.QUARTER:
            return QUARTERS_COUNT

        if row.period_type == PlanPeriodType.ALL_YEAR:
            return ACADEMIC_MONTHS_COUNT

        return 0

    @staticmethod
    def _build_direction_map(direction_rows) -> dict[int, str]:
        return {
            row.direction_id: row.direction_name
            for row in direction_rows
        }

    @classmethod
    def _build_period_statistics(
            cls,
            *,
            direction_map: dict[int, str],
            plan_rows,
    ) -> list[DirectionPeriodStatDTO]:
        stats_map: dict[int, DirectionPeriodStatDTO] = {
            direction_id: DirectionPeriodStatDTO(
                direction_id=direction_id,
                direction_name=direction_name,
            )
            for direction_id, direction_name in direction_map.items()
        }

        for row in plan_rows:
            direction_id = row.direction_id
            if direction_id is None:
                continue

            item = stats_map.setdefault(
                direction_id,
                DirectionPeriodStatDTO(
                    direction_id=direction_id,
                    direction_name=f"Направление {direction_id}",
                ),
            )

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

        return cls._ordered_direction_values(
            stats_map=stats_map,
            direction_map=direction_map,
        )

    @classmethod
    def _build_planned_statistics(
            cls,
            *,
            direction_map: dict[int, str],
            plan_rows,
    ) -> list[DirectionPlannedStatDTO]:
        stats_map: dict[int, int] = {
            direction_id: 0
            for direction_id in direction_map
        }

        for row in plan_rows:
            direction_id = row.direction_id
            if direction_id is None:
                continue

            stats_map[direction_id] = (
                    stats_map.get(direction_id, 0)
                    + cls._get_row_planned_count(row)
            )

        return [
            DirectionPlannedStatDTO(
                direction_id=direction_id,
                direction_name=direction_map.get(
                    direction_id,
                    f"Направление {direction_id}",
                ),
                planned_count=stats_map.get(direction_id, 0),
            )
            for direction_id in direction_map
        ]

    @classmethod
    def _build_review_place_statistics(
            cls,
            *,
            direction_map: dict[int, str],
            review_place_rows,
    ) -> list[DirectionReviewPlaceStatDTO]:
        stats_map: dict[int, DirectionReviewPlaceStatDTO] = {
            direction_id: DirectionReviewPlaceStatDTO(
                direction_id=direction_id,
                direction_name=direction_name,
            )
            for direction_id, direction_name in direction_map.items()
        }

        for row in review_place_rows:
            direction_id = row.direction_id
            if direction_id is None:
                continue

            item = stats_map.setdefault(
                direction_id,
                DirectionReviewPlaceStatDTO(
                    direction_id=direction_id,
                    direction_name=f"Направление {direction_id}",
                ),
            )

            place = ReviewPlace(getattr(row.review_place, 'value', row.review_place))
            field = place.value + '_count'
            setattr(item, field, getattr(item, field) + 1)

            item.total_review_places_count += 1

        return cls._ordered_direction_values(
            stats_map=stats_map,
            direction_map=direction_map,
        )

    @staticmethod
    def _ordered_direction_values(
            *,
            stats_map: dict[int, Any],
            direction_map: dict[int, str],
    ) -> list[Any]:
        result = [
            stats_map[direction_id]
            for direction_id in direction_map
            if direction_id in stats_map
        ]

        extra_direction_ids = sorted(
            set(stats_map) - set(direction_map)
        )
        result.extend(stats_map[direction_id] for direction_id in extra_direction_ids)

        return result

    @staticmethod
    def _build_review_place_totals(
            review_place_stats: list[DirectionReviewPlaceStatDTO],
    ) -> ReviewPlaceTotalsDTO:
        totals = ReviewPlaceTotalsDTO()

        for row in review_place_stats:
            for place in ReviewPlace:
                field = place.value + '_count'
                setattr(totals, field, getattr(totals, field) + getattr(row, field))
        totals.total_review_places_count = sum(
            getattr(totals, place.value + '_count') for place in ReviewPlace)

        return totals

    @classmethod
    async def get_period_statistics_by_direction(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
    ) -> list[DirectionPeriodStatDTO]:
        direction_rows = await cls.repository.get_directions(db)
        plan_rows = await cls.repository.get_plan_rows(
            db,
            school_plan_id=school_plan_id,
        )

        return cls._build_period_statistics(
            direction_map=cls._build_direction_map(direction_rows),
            plan_rows=plan_rows,
        )

    @classmethod
    async def get_planned_statistics_by_direction(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
    ) -> list[DirectionPlannedStatDTO]:
        direction_rows = await cls.repository.get_directions(db)
        plan_rows = await cls.repository.get_plan_rows(
            db,
            school_plan_id=school_plan_id,
        )

        return cls._build_planned_statistics(
            direction_map=cls._build_direction_map(direction_rows),
            plan_rows=plan_rows,
        )

    @classmethod
    async def get_review_place_statistics_by_direction(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
    ) -> list[DirectionReviewPlaceStatDTO]:
        direction_rows = await cls.repository.get_directions(db)
        review_place_rows = await cls.repository.get_review_place_rows(
            db,
            school_plan_id=school_plan_id,
        )

        return cls._build_review_place_statistics(
            direction_map=cls._build_direction_map(direction_rows),
            review_place_rows=review_place_rows,
        )

    @classmethod
    async def get_statistics_page_data(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
    ) -> dict[str, Any]:
        # Загружаем каждый набор данных один раз.
        direction_rows = await cls.repository.get_directions(db)
        plan_rows = await cls.repository.get_plan_rows(
            db,
            school_plan_id=school_plan_id,
        )
        review_place_rows = await cls.repository.get_review_place_rows(
            db,
            school_plan_id=school_plan_id,
        )

        direction_map = cls._build_direction_map(direction_rows)

        period_stats = cls._build_period_statistics(
            direction_map=direction_map,
            plan_rows=plan_rows,
        )
        planned_stats = cls._build_planned_statistics(
            direction_map=direction_map,
            plan_rows=plan_rows,
        )
        review_place_stats = cls._build_review_place_statistics(
            direction_map=direction_map,
            review_place_rows=review_place_rows,
        )

        totals = cls._build_review_place_totals(review_place_stats)
        comparison_stats = cls.build_statistics_comparison(
            period_stats=period_stats,
            planned_stats=planned_stats,
            review_place_stats=review_place_stats,
        )

        comparison_summary = {
            "total_directions": len(comparison_stats),
            "matched_count": sum(
                1 for item in comparison_stats if item["is_match"]
            ),
        }
        comparison_summary["mismatched_count"] = (
                comparison_summary["total_directions"]
                - comparison_summary["matched_count"]
        )

        return {
            "period_stats": period_stats,
            "planned_stats": planned_stats,
            "review_place_stats": review_place_stats,
            "review_place_totals": asdict(totals),
            "total_planned_count": sum(
                item.planned_count for item in planned_stats
            ),
            "total_review_places_count": totals.total_review_places_count,
            "comparison_stats": comparison_stats,
            "comparison_summary": comparison_summary,
        }

    @staticmethod
    def build_statistics_comparison(
            *,
            period_stats: list[DirectionPeriodStatDTO],
            planned_stats: list[DirectionPlannedStatDTO],
            review_place_stats: list[DirectionReviewPlaceStatDTO],
    ) -> list[dict[str, Any]]:
        planned_map = {
            item.direction_id: item
            for item in planned_stats
        }
        review_place_map = {
            item.direction_id: item
            for item in review_place_stats
        }

        result: list[dict[str, Any]] = []

        for period_item in period_stats:
            planned_item = planned_map.get(period_item.direction_id)
            review_place_item = review_place_map.get(period_item.direction_id)

            planned_count = (
                planned_item.planned_count
                if planned_item is not None
                else 0
            )
            period_total = (
                    period_item.month_count
                    + period_item.months_count
                    + period_item.monthly_count
                    + period_item.quarter_count
                    + period_item.all_year_count
            )
            review_place_total = (
                review_place_item.total_review_places_count
                if review_place_item is not None
                else 0
            )

            result.append(
                {
                    "direction_id": period_item.direction_id,
                    "direction_name": period_item.direction_name,
                    "period_total": period_total,
                    "planned_count": planned_count,
                    "review_place_total": review_place_total,
                    "is_match": period_total == review_place_total,
                    "diff": review_place_total - period_total,
                }
            )

        return result

    @staticmethod
    def build_direction_comparison(
            *,
            period_stats: list[DirectionPeriodStatDTO],
            planned_stats: list[DirectionPlannedStatDTO],
    ) -> list[dict[str, Any]]:
        planned_map = {
            item.direction_id: item
            for item in planned_stats
        }

        result: list[dict[str, Any]] = []

        for period_item in period_stats:
            planned_item = planned_map.get(period_item.direction_id)
            planned_count = (
                planned_item.planned_count
                if planned_item is not None
                else 0
            )
            period_total = (
                    period_item.month_count
                    + period_item.months_count
                    + period_item.monthly_count
                    + period_item.quarter_count
                    + period_item.all_year_count
            )

            result.append(
                {
                    "direction_id": period_item.direction_id,
                    "direction_name": period_item.direction_name,
                    "period_total": period_total,
                    "planned_count": planned_count,
                    "is_match": period_total == planned_count,
                    "diff": planned_count - period_total,
                }
            )

        return result


class SchoolExecutionStatisticsService:
    """
    Статистика выполнения и рассмотрения задач.

    Первая таблица:
        относительно годового плана.

    Вторая таблица:
        относительно каждого месячного плана.

    Третья таблица:
        выбранный месячный план по направлениям.
    """

    repository = SchoolStatisticsRepository
    planning_service = SchoolPlanStatisticsService

    @staticmethod
    def _calculate_percent(
            numerator: int,
            denominator: int,
    ) -> float:
        if denominator <= 0:
            return 0.0

        return round(
            numerator / denominator * 100,
            1,
        )

    @staticmethod
    def _get_enum_value(value) -> str:
        if value is None:
            return ""

        enum_value = getattr(value, "value", value)

        if isinstance(enum_value, tuple):
            return str(enum_value[0])

        return str(enum_value)

    @classmethod
    def _get_plan_status_label(cls, status) -> str:
        if status is None:
            return ""

        label = getattr(status, "label", None)
        if label:
            return str(label)

        enum_value = getattr(status, "value", status)

        if isinstance(enum_value, tuple):
            if len(enum_value) > 1:
                return str(enum_value[1])

            if enum_value:
                return str(enum_value[0])

        status_value = cls._get_enum_value(status)

        labels = {
            "draft": "Черновик",
            "approved": "Утверждён",
            "active": "В работе",
            "completed": "Завершён",
            "archived": "Архивный",
        }

        return labels.get(
            status_value,
            status_value,
        )

    @classmethod
    async def get_monthly_execution_statistics(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
    ) -> list[MonthlyExecutionStatDTO]:
        rows = await cls.repository.get_monthly_execution_counts(
            db,
            school_plan_id=school_plan_id,
        )

        result: list[MonthlyExecutionStatDTO] = []

        for row in rows:
            planned_count = int(row.planned_count or 0)
            completed_count = int(row.completed_count or 0)
            reviewed_count = int(row.reviewed_count or 0)

            not_completed_count = max(
                planned_count - completed_count,
                0,
            )

            result.append(
                MonthlyExecutionStatDTO(
                    month_plan_id=row.month_plan_id,
                    year=row.year,
                    month=row.month,
                    month_name=MONTH_LABELS.get(
                        row.month,
                        str(row.month),
                    ),
                    plan_status=cls._get_enum_value(
                        row.plan_status
                    ),
                    plan_status_label=cls._get_plan_status_label(
                        row.plan_status
                    ),
                    planned_count=planned_count,
                    completed_count=completed_count,
                    not_completed_count=not_completed_count,
                    reviewed_count=reviewed_count,
                    completion_percent=cls._calculate_percent(
                        completed_count,
                        planned_count,
                    ),
                    review_percent=cls._calculate_percent(
                        reviewed_count,
                        planned_count,
                    ),
                )
            )

        return result

    @classmethod
    async def get_annual_direction_statistics(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
    ) -> list[AnnualDirectionExecutionStatDTO]:
        """
        Первая таблица.

        annual_planned_count берётся из уже работающей
        статистики годового планирования.
        """

        annual_planned_stats = (
            await cls.planning_service
            .get_planned_statistics_by_direction(
                db,
                school_plan_id=school_plan_id,
            )
        )

        execution_rows = (
            await cls.repository
            .get_annual_direction_execution_counts(
                db,
                school_plan_id=school_plan_id,
            )
        )

        execution_map = {
            row.direction_id: row
            for row in execution_rows
        }

        result: list[AnnualDirectionExecutionStatDTO] = []

        for annual_item in annual_planned_stats:
            execution_row = execution_map.get(
                annual_item.direction_id
            )

            annual_planned_count = int(
                annual_item.planned_count or 0
            )

            included_count = (
                int(execution_row.included_count or 0)
                if execution_row is not None
                else 0
            )

            completed_count = (
                int(execution_row.completed_count or 0)
                if execution_row is not None
                else 0
            )

            reviewed_count = (
                int(execution_row.reviewed_count or 0)
                if execution_row is not None
                else 0
            )

            remaining_count = max(
                annual_planned_count - included_count,
                0,
            )

            result.append(
                AnnualDirectionExecutionStatDTO(
                    direction_id=annual_item.direction_id,
                    direction_name=annual_item.direction_name,
                    annual_planned_count=annual_planned_count,
                    included_count=included_count,
                    remaining_count=remaining_count,
                    completed_count=completed_count,
                    reviewed_count=reviewed_count,
                    planning_percent=cls._calculate_percent(
                        included_count,
                        annual_planned_count,
                    ),
                    completion_percent=cls._calculate_percent(
                        completed_count,
                        annual_planned_count,
                    ),
                    review_percent=cls._calculate_percent(
                        reviewed_count,
                        annual_planned_count,
                    ),
                )
            )

        return result

    @classmethod
    async def get_month_direction_statistics(
            cls,
            db: AsyncSession,
            *,
            month_plan_id: int,
    ) -> list[MonthDirectionExecutionStatDTO]:
        """
        Третья таблица.

        Добавляет все направления, даже если
        в выбранном месяце по направлению нет задач.
        """

        direction_rows = (
            await SchoolPlanStatisticsRepository
            .get_directions(db)
        )

        count_rows = (
            await cls.repository
            .get_month_direction_execution_counts(
                db,
                month_plan_id=month_plan_id,
            )
        )

        count_map = {
            row.direction_id: row
            for row in count_rows
        }

        result: list[MonthDirectionExecutionStatDTO] = []

        for direction in direction_rows:
            count_row = count_map.get(
                direction.direction_id
            )

            planned_count = (
                int(count_row.planned_count or 0)
                if count_row is not None
                else 0
            )

            completed_count = (
                int(count_row.completed_count or 0)
                if count_row is not None
                else 0
            )

            reviewed_count = (
                int(count_row.reviewed_count or 0)
                if count_row is not None
                else 0
            )

            result.append(
                MonthDirectionExecutionStatDTO(
                    direction_id=direction.direction_id,
                    direction_name=direction.direction_name,
                    planned_count=planned_count,
                    completed_count=completed_count,
                    not_completed_count=max(
                        planned_count - completed_count,
                        0,
                    ),
                    reviewed_count=reviewed_count,
                    completion_percent=cls._calculate_percent(
                        completed_count,
                        planned_count,
                    ),
                    review_percent=cls._calculate_percent(
                        reviewed_count,
                        planned_count,
                    ),
                )
            )

        return result

    @classmethod
    def build_totals(
            cls,
            rows,
            *,
            planned_field: str,
    ) -> dict[str, int | float]:
        planned_count = sum(
            int(getattr(row, planned_field, 0) or 0)
            for row in rows
        )

        completed_count = sum(
            int(row.completed_count or 0)
            for row in rows
        )

        reviewed_count = sum(
            int(row.reviewed_count or 0)
            for row in rows
        )

        return {
            "planned_count": planned_count,
            "completed_count": completed_count,
            "not_completed_count": max(
                planned_count - completed_count,
                0,
            ),
            "reviewed_count": reviewed_count,
            "completion_percent": cls._calculate_percent(
                completed_count,
                planned_count,
            ),
            "review_percent": cls._calculate_percent(
                reviewed_count,
                planned_count,
            ),
        }

    @classmethod
    async def get_execution_page_data(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
            selected_month_plan_id: int | None = None,
    ) -> dict[str, Any]:
        annual_stats = (
            await cls.get_annual_direction_statistics(
                db,
                school_plan_id=school_plan_id,
            )
        )

        monthly_stats = (
            await cls.get_monthly_execution_statistics(
                db,
                school_plan_id=school_plan_id,
            )
        )

        # По умолчанию раскрываем последний созданный
        # месяц в порядке учебного года.
        if (
                selected_month_plan_id is None
                and monthly_stats
        ):
            selected_month_plan_id = (
                monthly_stats[-1].month_plan_id
            )

        selected_month = next(
            (
                item
                for item in monthly_stats
                if item.month_plan_id == selected_month_plan_id
            ),
            None,
        )

        month_direction_stats = []

        if selected_month is not None:
            month_direction_stats = (
                await cls.get_month_direction_statistics(
                    db,
                    month_plan_id=selected_month.month_plan_id,
                )
            )

        annual_totals = cls.build_totals(
            annual_stats,
            planned_field="annual_planned_count",
        )

        annual_totals["included_count"] = sum(
            row.included_count
            for row in annual_stats
        )

        annual_totals["remaining_count"] = sum(
            row.remaining_count
            for row in annual_stats
        )

        annual_totals["planning_percent"] = (
            cls._calculate_percent(
                annual_totals["included_count"],
                annual_totals["planned_count"],
            )
        )

        monthly_totals = cls.build_totals(
            monthly_stats,
            planned_field="planned_count",
        )

        month_direction_totals = cls.build_totals(
            month_direction_stats,
            planned_field="planned_count",
        )

        return {
            "annual_stats": annual_stats,
            "annual_totals": annual_totals,

            "monthly_stats": monthly_stats,
            "monthly_totals": monthly_totals,

            "selected_month_plan_id": (
                selected_month_plan_id
            ),
            "selected_month": selected_month,

            "month_direction_stats": (
                month_direction_stats
            ),
            "month_direction_totals": (
                month_direction_totals
            ),
        }

    @classmethod
    def build_monthly_execution_totals(
            cls,
            statistics: list[MonthlyExecutionStatDTO],
    ) -> dict[str, int | float]:
        """
        Формирует итоговую строку статистики
        по всем созданным месячным планам.
        """

        planned_count = sum(
            item.planned_count
            for item in statistics
        )

        completed_count = sum(
            item.completed_count
            for item in statistics
        )

        reviewed_count = sum(
            item.reviewed_count
            for item in statistics
        )

        not_completed_count = max(
            planned_count - completed_count,
            0,
        )

        return {
            "planned_count": planned_count,
            "completed_count": completed_count,
            "not_completed_count": not_completed_count,
            "reviewed_count": reviewed_count,
            "completion_percent": cls._calculate_percent(
                completed_count,
                planned_count,
            ),
            "review_percent": cls._calculate_percent(
                reviewed_count,
                planned_count,
            ),
        }


class StaffExecutionStatisticsService:
    """
    Личная статистика выполнения и рассмотрения задач сотрудника.

    Учитываются задачи, где пользователь:
    - основной ответственный;
    - исполнитель;
    - соисполнитель.
    """

    repository = StaffStatisticsRepository
    direction_repository = SchoolPlanStatisticsRepository

    @staticmethod
    def _calculate_percent(
            numerator: int,
            denominator: int,
    ) -> float:
        if denominator <= 0:
            return 0.0

        return round(
            numerator / denominator * 100,
            1,
        )

    @staticmethod
    def _get_enum_value(value) -> str:
        if value is None:
            return ""

        enum_value = getattr(value, "value", value)

        if isinstance(enum_value, tuple):
            return str(enum_value[0])

        return str(enum_value)

    @classmethod
    def _get_plan_status_label(cls, status) -> str:
        if status is None:
            return ""

        label = getattr(status, "label", None)

        if label:
            return str(label)

        enum_value = getattr(status, "value", status)

        if isinstance(enum_value, tuple):
            if len(enum_value) > 1:
                return str(enum_value[1])

            if enum_value:
                return str(enum_value[0])

        status_value = cls._get_enum_value(status)

        labels = {
            "draft": "Черновик",
            "approved": "Утверждён",
            "active": "В работе",
            "completed": "Завершён",
            "archived": "Архивный",
        }

        return labels.get(
            status_value,
            status_value,
        )

    @classmethod
    async def get_monthly_statistics(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
            user_id: int,
    ) -> list[StaffMonthlyExecutionStatDTO]:
        """
        Личная статистика сотрудника по месяцам.
        """

        rows = await cls.repository.get_monthly_execution_counts(
            db,
            school_plan_id=school_plan_id,
            user_id=user_id,
        )

        result: list[StaffMonthlyExecutionStatDTO] = []

        for row in rows:
            assigned_count = int(
                row.assigned_count or 0
            )

            completed_count = int(
                row.completed_count or 0
            )

            reviewed_count = int(
                row.reviewed_count or 0
            )

            not_completed_count = max(
                assigned_count - completed_count,
                0,
            )

            result.append(
                StaffMonthlyExecutionStatDTO(
                    month_plan_id=row.month_plan_id,
                    year=row.year,
                    month=row.month,
                    month_name=MONTH_LABELS.get(
                        row.month,
                        str(row.month),
                    ),
                    plan_status=cls._get_enum_value(
                        row.plan_status
                    ),
                    plan_status_label=cls._get_plan_status_label(
                        row.plan_status
                    ),
                    assigned_count=assigned_count,
                    completed_count=completed_count,
                    not_completed_count=not_completed_count,
                    reviewed_count=reviewed_count,
                    completion_percent=cls._calculate_percent(
                        completed_count,
                        assigned_count,
                    ),
                    review_percent=cls._calculate_percent(
                        reviewed_count,
                        completed_count,
                    ),
                )
            )

        return result

    @classmethod
    async def get_month_direction_statistics(
            cls,
            db: AsyncSession,
            *,
            month_plan_id: int,
            user_id: int,
    ) -> list[StaffMonthDirectionStatDTO]:
        """
        Личная статистика сотрудника
        по направлениям выбранного месяца.
        """

        direction_rows = await cls.direction_repository.get_directions(
            db
        )

        count_rows = (
            await cls.repository
            .get_month_direction_execution_counts(
                db,
                month_plan_id=month_plan_id,
                user_id=user_id,
            )
        )

        count_map = {
            row.direction_id: row
            for row in count_rows
        }

        result: list[StaffMonthDirectionStatDTO] = []

        for direction in direction_rows:
            count_row = count_map.get(
                direction.direction_id
            )

            assigned_count = (
                int(count_row.assigned_count or 0)
                if count_row is not None
                else 0
            )

            completed_count = (
                int(count_row.completed_count or 0)
                if count_row is not None
                else 0
            )

            reviewed_count = (
                int(count_row.reviewed_count or 0)
                if count_row is not None
                else 0
            )

            result.append(
                StaffMonthDirectionStatDTO(
                    direction_id=direction.direction_id,
                    direction_name=direction.direction_name,
                    assigned_count=assigned_count,
                    completed_count=completed_count,
                    not_completed_count=max(
                        assigned_count - completed_count,
                        0,
                    ),
                    reviewed_count=reviewed_count,
                    completion_percent=cls._calculate_percent(
                        completed_count,
                        assigned_count,
                    ),
                    review_percent=cls._calculate_percent(
                        reviewed_count,
                        completed_count,
                    ),
                )
            )

        return result

    @classmethod
    def build_totals(
            cls,
            rows,
            *,
            assigned_field: str = "assigned_count",
    ) -> dict[str, int | float]:
        """
        Формирует итоговые показатели списка статистики.
        """

        assigned_count = sum(
            int(
                getattr(
                    row,
                    assigned_field,
                    0,
                )
                or 0
            )
            for row in rows
        )

        completed_count = sum(
            int(row.completed_count or 0)
            for row in rows
        )

        reviewed_count = sum(
            int(row.reviewed_count or 0)
            for row in rows
        )

        not_completed_count = max(
            assigned_count - completed_count,
            0,
        )

        return {
            "assigned_count": assigned_count,
            "completed_count": completed_count,
            "not_completed_count": not_completed_count,
            "reviewed_count": reviewed_count,
            "completion_percent": cls._calculate_percent(
                completed_count,
                assigned_count,
            ),
            "review_percent": cls._calculate_percent(
                reviewed_count,
                assigned_count,
            ),
        }

    @classmethod
    async def get_page_data(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
            user_id: int,
            selected_month_plan_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Собирает данные страницы «Моя статистика».
        """

        monthly_stats = await cls.get_monthly_statistics(
            db,
            school_plan_id=school_plan_id,
            user_id=user_id,
        )

        # По умолчанию раскрываем последний месяц,
        # в котором у сотрудника есть назначенные задачи.
        if selected_month_plan_id is None:
            selected_with_tasks = [
                item
                for item in monthly_stats
                if item.assigned_count > 0
            ]

            if selected_with_tasks:
                selected_month_plan_id = (
                    selected_with_tasks[-1].month_plan_id
                )

        selected_month = next(
            (
                item
                for item in monthly_stats
                if item.month_plan_id == selected_month_plan_id
            ),
            None,
        )

        month_direction_stats: list[
            StaffMonthDirectionStatDTO
        ] = []

        if selected_month is not None:
            month_direction_stats = (
                await cls.get_month_direction_statistics(
                    db,
                    month_plan_id=selected_month.month_plan_id,
                    user_id=user_id,
                )
            )

        monthly_totals = cls.build_totals(
            monthly_stats
        )

        month_direction_totals = cls.build_totals(
            month_direction_stats
        )

        return {
            "monthly_stats": monthly_stats,
            "monthly_totals": monthly_totals,

            "selected_month_plan_id": (
                selected_month_plan_id
            ),
            "selected_month": selected_month,

            "month_direction_stats": (
                month_direction_stats
            ),
            "month_direction_totals": (
                month_direction_totals
            ),
        }
