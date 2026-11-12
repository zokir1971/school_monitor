# app/modules/assessment/schemas/manual_result_schemas.py

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.modules.assessment.enums import (
    AssessmentParticipationStatus,
)


# =========================================================
# MANUAL INPUT
# =========================================================


@dataclass(frozen=True, slots=True)
class ManualObjectiveScoreDTO:
    """
    Балл ученика по одной учебной цели.

    Используется только для Assessment,
    работающих с учебными целями:

        ASSESSMENT_BY_SECTION
        ASSESSMENT_BY_QUARTER

    Клиент передаёт только:
        assessment_objective_id
        score

    max_score и percent определяет backend
    по AssessmentObjective.
    """

    assessment_objective_id: int

    score: Decimal


@dataclass(frozen=True, slots=True)
class ManualStudentResultDTO:
    """
    Результат одного участника Assessment.

    WITHOUT_OBJECTIVES:

        COMPLETED
            score обязателен
            objective_scores пуст

        ABSENT / EXCUSED / NOT_COMPLETED
            score = None
            objective_scores пуст


    ASSESSMENT_BY_SECTION /
    ASSESSMENT_BY_QUARTER:

        COMPLETED
            score от клиента не используется
            objective_scores обязательны

        Backend самостоятельно рассчитывает:

            total_score =
                sum(objective_scores)

            percent
            grade

        ABSENT / EXCUSED / NOT_COMPLETED:
            score = None
            objective_scores пуст
    """

    assessment_student_id: int

    participation_status: (
        AssessmentParticipationStatus
    )

    # Для WITHOUT_OBJECTIVES.
    score: Decimal | None = None

    # Для SECTION / QUARTER.
    objective_scores: tuple[
        ManualObjectiveScoreDTO,
        ...
    ] = field(
        default_factory=tuple,
    )


@dataclass(frozen=True, slots=True)
class ManualAssessmentSaveDTO:
    """
    Пакет ручных результатов
    одного Assessment.
    """

    assessment_id: int

    results: tuple[
        ManualStudentResultDTO,
        ...
    ] = field(
        default_factory=tuple,
    )


# =========================================================
# PAGE DTOs
# =========================================================


@dataclass(frozen=True, slots=True)
class ManualAssessmentObjectiveDTO:
    """
    Учебная цель Assessment
    для страницы ручного ввода.

    Это snapshot структуры Assessment,
    а не глобальный LearningObjective.
    """

    assessment_objective_id: int

    learning_objective_id: int

    code: str
    title: str

    max_score: Decimal

    order_no: int

    @property
    def max_score_display(self) -> str:
        if (
            self.max_score
            == self.max_score.to_integral_value()
        ):
            return str(
                int(
                    self.max_score
                )
            )

        return format(
            self.max_score.normalize(),
            "f",
        ).replace(
            ".",
            ",",
        )


@dataclass(frozen=True, slots=True)
class ManualStudentObjectiveResultDTO:
    """
    Существующий результат ученика
    по одной учебной цели.

    Используется при повторном открытии
    страницы ручного ввода.
    """

    assessment_objective_id: int

    score: Decimal | None = None

    max_score: Decimal | None = None

    percent: Decimal | None = None

    @property
    def score_display(self) -> str:
        if self.score is None:
            return "—"

        if (
            self.score
            == self.score.to_integral_value()
        ):
            return str(
                int(
                    self.score
                )
            )

        return format(
            self.score.normalize(),
            "f",
        ).replace(
            ".",
            ",",
        )

    @property
    def percent_display(self) -> str:
        if self.percent is None:
            return "—"

        return (
            f"{self.percent:.2f}"
            .replace(
                ".",
                ",",
            )
            + "%"
        )


@dataclass(frozen=True, slots=True)
class ManualAssessmentStudentRowDTO:
    """
    Одна строка ученика
    на странице ручного ввода.

    Для WITHOUT_OBJECTIVES:
        используется score.

    Для SECTION / QUARTER:
        используются objective_results.

    Общий score / percent / grade
    являются итогом AssessmentResult.
    """

    assessment_student_id: int
    student_id: int

    student_name: str

    participation_status: str
    participation_status_label: str

    # =====================================================
    # TOTAL RESULT
    # =====================================================

    score: Decimal | None = None

    percent: Decimal | None = None

    grade: str | None = None
    grade_label: str | None = None

    # =====================================================
    # OBJECTIVE RESULTS
    # =====================================================

    objective_results: tuple[
        ManualStudentObjectiveResultDTO,
        ...
    ] = field(
        default_factory=tuple,
    )

    # =====================================================
    # DISPLAY
    # =====================================================

    @property
    def score_display(self) -> str:
        if self.score is None:
            return "—"

        if (
            self.score
            == self.score.to_integral_value()
        ):
            return str(
                int(
                    self.score
                )
            )

        return format(
            self.score.normalize(),
            "f",
        ).replace(
            ".",
            ",",
        )

    @property
    def percent_display(self) -> str:
        if self.percent is None:
            return "—"

        return (
            f"{self.percent:.2f}"
            .replace(
                ".",
                ",",
            )
            + "%"
        )

    @property
    def grade_display(self) -> str:
        if self.grade is None:
            return "—"

        if self.grade_label:
            return (
                f"{self.grade} "
                f"({self.grade_label})"
            )

        return self.grade


@dataclass(frozen=True, slots=True)
class ManualAssessmentGroupDTO:
    """
    Один класс внутри Assessment.
    """

    assessment_group_id: int
    school_class_id: int

    class_name: str

    academic_year_start: int

    teacher_name: str | None

    students: tuple[
        ManualAssessmentStudentRowDTO,
        ...
    ] = field(
        default_factory=tuple,
    )


@dataclass(frozen=True, slots=True)
class ManualAssessmentPageDTO:
    """
    Полные данные страницы
    ручного ввода Assessment.

    assessment_mode используется шаблоном
    для выбора интерфейса:

        WITHOUT_OBJECTIVES
            → одно поле общего балла;

        ASSESSMENT_BY_SECTION /
        ASSESSMENT_BY_QUARTER
            → колонки учебных целей.
    """

    assessment_id: int

    title: str
    description: str | None

    subject_id: int
    subject_name: str

    max_score: Decimal | None

    # =====================================================
    # TYPE / MODE
    # =====================================================

    assessment_type: str
    assessment_type_label: str

    assessment_mode: str

    duration_minutes: int | None

    # =====================================================
    # STATUS
    # =====================================================

    status: str
    status_label: str

    # =====================================================
    # OBJECTIVES
    # =====================================================

    objectives: tuple[
        ManualAssessmentObjectiveDTO,
        ...
    ] = field(
        default_factory=tuple,
    )

    # =====================================================
    # GROUPS
    # =====================================================

    groups: tuple[
        ManualAssessmentGroupDTO,
        ...
    ] = field(
        default_factory=tuple,
    )

    # =====================================================
    # DISPLAY
    # =====================================================

    @property
    def max_score_display(self) -> str:
        if self.max_score is None:
            return "—"

        if (
            self.max_score
            == self.max_score.to_integral_value()
        ):
            return str(
                int(
                    self.max_score
                )
            )

        return format(
            self.max_score.normalize(),
            "f",
        ).replace(
            ".",
            ",",
        )

    @property
    def duration_display(self) -> str:
        if self.duration_minutes is None:
            return "—"

        return (
            f"{self.duration_minutes} мин."
        )

    @property
    def has_objectives(self) -> bool:
        return bool(
            self.objectives
        )
