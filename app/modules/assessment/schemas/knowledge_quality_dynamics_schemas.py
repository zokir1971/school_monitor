# app/modules/assessment/schemas/knowledge_quality_dynamics_schemas.py

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.modules.assessment.enums import (
    AssessmentCheckpoint,
)


# =========================================================
# DISPLAY HELPERS
# =========================================================


def _percent_display(
        value: Decimal | None,
) -> str:
    """
    Форматирование процентного значения для UI.
    """
    if value is None:
        return "—"

    return (
        f"{value:.2f}"
        .replace(".", ",")
        + "%"
    )


def _delta_display(
        value: Decimal | None,
) -> str:
    """
    Форматирование изменения в процентных пунктах для UI.
    """
    if value is None:
        return "—"

    prefix = "+" if value > 0 else ""

    return (
        prefix
        + f"{value:.2f}"
        .replace(".", ",")
        + " п.п."
    )


# =========================================================
# CHECKPOINT
# =========================================================


@dataclass(frozen=True, slots=True)
class KnowledgeQualityCheckpointDTO:
    """
    Одна контрольная точка динамики качества знаний.

    quality_percent:
        качество знаний на текущей точке.

    delta_previous_pp:
        изменение в процентных пунктах
        относительно предыдущей доступной точки.

    delta_baseline_pp:
        изменение в процентных пунктах
        относительно Нөлдік бақылау.

    Для baseline:
        delta_previous_pp = None
        delta_baseline_pp = 0.00

    Если baseline отсутствует:
        delta_baseline_pp = None
    """

    checkpoint: AssessmentCheckpoint
    checkpoint_label: str

    total_students: int
    participated_students: int
    quality_students: int

    quality_percent: Decimal | None

    delta_previous_pp: Decimal | None
    delta_baseline_pp: Decimal | None

    # =====================================================
    # DISPLAY
    # =====================================================

    @property
    def quality_percent_display(self) -> str:
        return _percent_display(
            self.quality_percent
        )

    @property
    def delta_previous_display(self) -> str:
        return _delta_display(
            self.delta_previous_pp
        )

    @property
    def delta_baseline_display(self) -> str:
        return _delta_display(
            self.delta_baseline_pp
        )

    @property
    def participation_display(self) -> str:
        return (
            f"{self.participated_students}/"
            f"{self.total_students}"
        )


# =========================================================
# DYNAMICS SERIES
# =========================================================


@dataclass(frozen=True, slots=True)
class KnowledgeQualityDynamicsDTO:
    """
    Динамика качества знаний одного аналитического scope.

    scope:
        school
        district
        region

    Может дополнительно быть отфильтрована по:
        subject
        grade
        class
        teacher
        district
        school

    points всегда должны быть расположены
    в бизнес-порядке:

        BASELINE
        QUARTER_1
        QUARTER_2
        QUARTER_3
        QUARTER_4
        FINAL
    """

    scope: str

    academic_year_start: int

    school_id: int | None = None
    district_id: int | None = None
    region_id: int | None = None

    subject_id: int | None = None
    grade_level: int | None = None

    school_class_id: int | None = None
    teacher_staff_member_id: int | None = None

    points: tuple[
        KnowledgeQualityCheckpointDTO,
        ...
    ] = ()

    # =====================================================
    # HELPERS
    # =====================================================

    @property
    def point_count(self) -> int:
        return len(
            self.points
        )

    @property
    def has_data(self) -> bool:
        return bool(
            self.points
        )

    @property
    def baseline_point(
            self,
    ) -> KnowledgeQualityCheckpointDTO | None:
        for point in self.points:
            if (
                point.checkpoint
                == AssessmentCheckpoint.BASELINE
            ):
                return point

        return None

    @property
    def latest_point(
            self,
    ) -> KnowledgeQualityCheckpointDTO | None:
        if not self.points:
            return None

        return self.points[-1]

    @property
    def baseline_quality_percent(
            self,
    ) -> Decimal | None:
        baseline = self.baseline_point

        if baseline is None:
            return None

        return baseline.quality_percent

    @property
    def latest_quality_percent(
            self,
    ) -> Decimal | None:
        latest = self.latest_point

        if latest is None:
            return None

        return latest.quality_percent

    @property
    def total_delta_baseline_pp(
            self,
    ) -> Decimal | None:
        latest = self.latest_point

        if latest is None:
            return None

        return latest.delta_baseline_pp

    # =====================================================
    # DISPLAY
    # =====================================================

    @property
    def baseline_quality_percent_display(
            self,
    ) -> str:
        return _percent_display(
            self.baseline_quality_percent
        )

    @property
    def latest_quality_percent_display(
            self,
    ) -> str:
        return _percent_display(
            self.latest_quality_percent
        )

    @property
    def total_delta_baseline_display(
            self,
    ) -> str:
        return _delta_display(
            self.total_delta_baseline_pp
        )


# =========================================================
# ENTITY DRILL-DOWN
# =========================================================


@dataclass(frozen=True, slots=True)
class KnowledgeQualityEntityDynamicsItemDTO:
    """
    Динамика одной drill-down сущности.

    entity_id:
        school_id   — для district -> schools;
        district_id — для region -> districts;
        school_id   — для region -> district -> schools.
    """

    entity_id: int
    entity_name: str

    points: tuple[
        KnowledgeQualityCheckpointDTO,
        ...
    ] = ()

    # =====================================================
    # HELPERS
    # =====================================================

    @property
    def point_count(self) -> int:
        return len(
            self.points
        )

    @property
    def has_data(self) -> bool:
        return bool(
            self.points
        )

    @property
    def baseline_point(
            self,
    ) -> KnowledgeQualityCheckpointDTO | None:
        for point in self.points:
            if (
                point.checkpoint
                == AssessmentCheckpoint.BASELINE
            ):
                return point

        return None

    @property
    def latest_point(
            self,
    ) -> KnowledgeQualityCheckpointDTO | None:
        if not self.points:
            return None

        return self.points[-1]

    @property
    def baseline_quality_percent(
            self,
    ) -> Decimal | None:
        baseline = self.baseline_point

        if baseline is None:
            return None

        return baseline.quality_percent

    @property
    def latest_quality_percent(
            self,
    ) -> Decimal | None:
        latest = self.latest_point

        if latest is None:
            return None

        return latest.quality_percent

    @property
    def total_delta_baseline_pp(
            self,
    ) -> Decimal | None:
        latest = self.latest_point

        if latest is None:
            return None

        return latest.delta_baseline_pp

    # =====================================================
    # DISPLAY
    # =====================================================

    @property
    def baseline_quality_percent_display(
            self,
    ) -> str:
        return _percent_display(
            self.baseline_quality_percent
        )

    @property
    def latest_quality_percent_display(
            self,
    ) -> str:
        return _percent_display(
            self.latest_quality_percent
        )

    @property
    def total_delta_baseline_display(
            self,
    ) -> str:
        return _delta_display(
            self.total_delta_baseline_pp
        )


# =========================================================
# ENTITY DYNAMICS
# =========================================================


@dataclass(frozen=True, slots=True)
class KnowledgeQualityEntityDynamicsDTO:
    """
    Drill-down динамики по организационным сущностям.

    scope:
        district_schools
        region_districts
        region_schools
    """

    scope: str
    parent_id: int

    academic_year_start: int

    subject_id: int | None = None
    grade_level: int | None = None

    items: tuple[
        KnowledgeQualityEntityDynamicsItemDTO,
        ...
    ] = ()

    @property
    def item_count(self) -> int:
        return len(
            self.items
        )

    @property
    def has_data(self) -> bool:
        return bool(
            self.items
        )


# =========================================================
# FILTER OPTIONS
# =========================================================


@dataclass(frozen=True, slots=True)
class KnowledgeQualityDynamicsFilterOptionsDTO:
    """
    Доступные фильтры страницы динамики качества знаний школы.

    selected_* уже нормализованы Service Layer:
        - учебный год должен существовать в dynamics data;
        - subject должен существовать в выбранном учебном году;
        - grade должен существовать в выбранном учебном году
          и, если выбран предмет, внутри выбранного предмета.
    """

    academic_years: tuple[int, ...]
    subject_ids: tuple[int, ...]
    grade_levels: tuple[int, ...]

    selected_academic_year: int | None
    selected_subject_id: int | None
    selected_grade_level: int | None

    @property
    def has_data(self) -> bool:
        return bool(
            self.academic_years
            and self.selected_academic_year is not None
        )
