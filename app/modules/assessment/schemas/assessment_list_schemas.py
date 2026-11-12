# app/modules/assessment/schemas/assessment_list_schemas.py

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


# =========================================================
# FILTER OPTIONS
# =========================================================


@dataclass(frozen=True, slots=True)
class AssessmentListSubjectOptionDTO:
    """
    Предмет, реально присутствующий
    в существующих Assessment.
    """

    subject_id: int
    subject_name: str


@dataclass(frozen=True, slots=True)
class AssessmentListFilterOptionsDTO:
    """
    Доступные значения фильтров списка Assessment.

    Источник данных:
        Assessment
        AssessmentGroup snapshots

    Это принципиально не текущие active Subject / SchoolClass,
    потому что список должен корректно работать
    и для исторических Assessment.
    """

    academic_years: tuple[int, ...] = field(
        default_factory=tuple,
    )

    subjects: tuple[
        AssessmentListSubjectOptionDTO,
        ...
    ] = field(
        default_factory=tuple,
    )

    grade_levels: tuple[int, ...] = field(
        default_factory=tuple,
    )


# =========================================================
# LIST ITEM
# =========================================================


@dataclass(frozen=True, slots=True)
class AssessmentListItemDTO:
    """
    Одна строка списка Assessment.

    DTO общий для:
        - school admin;
        - school staff;
        - teacher.

    Различия доступа определяет Service Layer.
    """

    assessment_id: int

    title: str

    subject_id: int
    subject_name: str

    assessment_type: str
    assessment_type_label: str

    status: str
    status_label: str

    input_mode: str
    input_mode_label: str

    max_score: Decimal | None

    class_names: tuple[str, ...] = field(
        default_factory=tuple,
    )

    teacher_names: tuple[str, ...] = field(
        default_factory=tuple,
    )

    total_students: int = 0
    completed_students: int = 0
    absent_students: int = 0
    result_count: int = 0
    processed_students: int = 0

    # -----------------------------------------------------
    # ACCESS / ACTIONS
    # -----------------------------------------------------

    can_complete: bool = False

    @property
    def max_score_display(self) -> str:
        if self.max_score is None:
            return "—"

        if (
            self.max_score
            == self.max_score.to_integral_value()
        ):
            return str(
                int(self.max_score)
            )

        return format(
            self.max_score.normalize(),
            "f",
        ).replace(
            ".",
            ",",
        )

    @property
    def class_names_display(self) -> str:
        if not self.class_names:
            return "—"

        return ", ".join(
            self.class_names
        )

    @property
    def teacher_names_display(self) -> str:
        if not self.teacher_names:
            return "—"

        return ", ".join(
            self.teacher_names
        )

    @property
    def result_progress_display(self) -> str:
        return (
            f"{self.processed_students}/"
            f"{self.total_students}"
        )

    @property
    def pending_students(self) -> int:
        pending = (
            self.total_students
            - self.processed_students
        )

        return max(
            pending,
            0,
        )

    @property
    def is_fully_processed(self) -> bool:
        return (
            0
            < self.total_students
            == self.processed_students
        )


# =========================================================
# PAGE
# =========================================================


@dataclass(frozen=True, slots=True)
class AssessmentListPageDTO:
    """
    Данные страницы списка Assessment.

    Один DTO используется для school staff/admin
    и teacher list.
    """

    school_id: int

    items: tuple[
        AssessmentListItemDTO,
        ...
    ] = field(
        default_factory=tuple,
    )

    filter_options: AssessmentListFilterOptionsDTO = field(
        default_factory=AssessmentListFilterOptionsDTO,
    )

    total_count: int = 0
    draft_count: int = 0
    completed_count: int = 0

    selected_academic_year: int | None = None
    selected_subject_id: int | None = None
    selected_grade_level: int | None = None
    selected_status: str | None = None

    @property
    def academic_years(self) -> tuple[int, ...]:
        return self.filter_options.academic_years

    @property
    def subjects(
        self,
    ) -> tuple[
        AssessmentListSubjectOptionDTO,
        ...
    ]:
        return self.filter_options.subjects

    @property
    def grade_levels(self) -> tuple[int, ...]:
        return self.filter_options.grade_levels
