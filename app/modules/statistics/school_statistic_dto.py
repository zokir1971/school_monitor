# app/modules/statistics/school_statistic_dto.py
from __future__ import annotations

from dataclasses import dataclass


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


@dataclass
class DirectionComparisonStatDTO:
    direction_id: int
    direction_name: str
    period_total: int
    planned_count: int
    is_match: bool
    diff: int


@dataclass(slots=True, frozen=True)
class AnnualDirectionExecutionStatDTO:
    direction_id: int
    direction_name: str

    annual_planned_count: int = 0
    included_count: int = 0
    remaining_count: int = 0

    completed_count: int = 0
    reviewed_count: int = 0

    planning_percent: float = 0.0
    completion_percent: float = 0.0
    review_percent: float = 0.0


@dataclass(slots=True, frozen=True)
class MonthlyExecutionStatDTO:
    month_plan_id: int

    year: int
    month: int
    month_name: str

    plan_status: str
    plan_status_label: str

    planned_count: int
    completed_count: int
    not_completed_count: int
    reviewed_count: int

    completion_percent: float
    review_percent: float


@dataclass(slots=True, frozen=True)
class MonthDirectionExecutionStatDTO:
    direction_id: int
    direction_name: str

    planned_count: int = 0
    completed_count: int = 0
    not_completed_count: int = 0
    reviewed_count: int = 0

    completion_percent: float = 0.0
    review_percent: float = 0.0


@dataclass(slots=True, frozen=True)
class StaffMonthlyExecutionStatDTO:
    month_plan_id: int

    year: int
    month: int
    month_name: str

    plan_status: str
    plan_status_label: str

    assigned_count: int
    completed_count: int
    not_completed_count: int
    reviewed_count: int

    completion_percent: float
    review_percent: float


@dataclass(slots=True, frozen=True)
class StaffMonthDirectionStatDTO:
    direction_id: int
    direction_name: str

    assigned_count: int
    completed_count: int
    not_completed_count: int
    reviewed_count: int

    completion_percent: float
    review_percent: float
