# app/modules/assessment/schemas/teacher_result_schemas.py

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.modules.assessment.enums import (
    AssessmentGrade,
    AssessmentParticipationStatus, AssessmentAnswerStatus, AssessmentQuestionType, AssessmentInputMode,
)


@dataclass(frozen=True, slots=True)
class TeacherClassAssessmentItemDTO:
    assessment_id: int
    assessment_group_id: int

    title: str
    subject_name: str

    school_class_id: int
    class_name: str
    grade_level: int

    max_score: Decimal | None

    total_students: int
    participated_students: int

    @property
    def participation_display(self) -> str:
        return (
            f"{self.participated_students}/"
            f"{self.total_students}"
        )

    @property
    def max_score_display(self) -> str:
        if self.max_score is None:
            return "—"

        value = self.max_score.quantize(
            Decimal("0.01")
        )

        text = format(
            value,
            "f",
        ).rstrip("0").rstrip(".")

        return text.replace(
            ".",
            ",",
        )


@dataclass(frozen=True, slots=True)
class TeacherClassAssessmentsPageDTO:
    school_class_id: int
    class_name: str

    academic_year_start: int | None = None
    subject_id: int | None = None

    items: tuple[
        TeacherClassAssessmentItemDTO,
        ...
    ] = field(
        default_factory=tuple,
    )

    @property
    def item_count(self) -> int:
        return len(
            self.items
        )


@dataclass(frozen=True, slots=True)
class TeacherStudentResultDTO:
    assessment_student_id: int
    student_id: int
    student_name: str

    participation_status: AssessmentParticipationStatus

    score: Decimal | None
    max_score: Decimal | None
    percent: Decimal | None

    grade: AssessmentGrade | None

    @property
    def score_display(self) -> str:
        if (
                self.score is None
                or self.max_score is None
        ):
            return "—"

        score = format(
            self.score.quantize(
                Decimal("0.01")
            ),
            "f",
        ).rstrip("0").rstrip(".")

        max_score = format(
            self.max_score.quantize(
                Decimal("0.01")
            ),
            "f",
        ).rstrip("0").rstrip(".")

        return (
            f"{score.replace('.', ',')}/"
            f"{max_score.replace('.', ',')}"
        )

    @property
    def percent_display(self) -> str:
        if self.percent is None:
            return "—"

        return (
                format(
                    self.percent.quantize(
                        Decimal("0.01")
                    ),
                    ".2f",
                ).replace(
                    ".",
                    ",",
                )
                + "%"
        )

    @property
    def grade_display(self) -> str:
        if self.grade is None:
            return "—"

        value = (
            self.grade.value
            if hasattr(
                self.grade,
                "value",
            )
            else str(
                self.grade
            )
        )

        return value

    @property
    def participation_status_display(self) -> str:
        value = (
            self.participation_status.value
            if hasattr(
                self.participation_status,
                "value",
            )
            else str(
                self.participation_status
            )
        )

        labels = {
            "assigned": "Тағайындалды",
            "in_progress": "Орындалуда",
            "completed": "Орындалды",
            "absent": "Қатыспады",
            "excused": "Себепті",
            "not_completed": "Аяқтамады",
        }

        return labels.get(
            value,
            value,
        )


@dataclass(frozen=True, slots=True)
class TeacherAssessmentStudentsPageDTO:
    assessment_id: int
    assessment_group_id: int

    title: str
    subject_name: str
    input_mode: AssessmentInputMode

    school_class_id: int
    class_name: str
    grade_level: int

    max_score: Decimal | None

    students: tuple[
        TeacherStudentResultDTO,
        ...
    ] = field(
        default_factory=tuple,
    )

    @property
    def student_count(self) -> int:
        return len(
            self.students
        )

    @property
    def is_online(self) -> bool:
        return (
            self.input_mode
            == AssessmentInputMode.ONLINE
        )

    @property
    def max_score_display(self) -> str:
        if self.max_score is None:
            return "—"

        value = self.max_score.quantize(
            Decimal("0.01")
        )

        text = format(
            value,
            "f",
        ).rstrip("0").rstrip(".")

        return text.replace(
            ".",
            ",",
        )


# =========================================================
# OBJECTIVE SUMMARY
# =========================================================

@dataclass(frozen=True, slots=True)
class TeacherObjectiveSummaryDTO:
    """
    Агрегированная аналитика одной учебной цели
    внутри конкретной AssessmentGroup.
    """

    assessment_id: int
    assessment_group_id: int

    assessment_title: str
    subject_name: str

    school_class_id: int
    class_name: str
    grade_level: int

    assessment_objective_id: int
    learning_objective_id: int

    objective_code: str
    objective_title: str
    order_no: int

    objective_max_score: Decimal

    participated_students: int

    score_sum: Decimal
    max_score_sum: Decimal

    mastery_percent: Decimal | None

    @property
    def objective_max_score_display(self) -> str:
        return self._format_decimal(
            self.objective_max_score
        )

    @property
    def score_sum_display(self) -> str:
        return self._format_decimal(
            self.score_sum
        )

    @property
    def max_score_sum_display(self) -> str:
        return self._format_decimal(
            self.max_score_sum
        )

    @property
    def mastery_percent_display(self) -> str:
        if self.mastery_percent is None:
            return "—"

        return (
                f"{self.mastery_percent:.2f}"
                .replace(".", ",")
                + "%"
        )

    @staticmethod
    def _format_decimal(
            value: Decimal,
    ) -> str:
        if (
                value
                == value.to_integral_value()
        ):
            return str(
                int(value)
            )

        return format(
            value.normalize(),
            "f",
        ).replace(
            ".",
            ",",
        )


# =========================================================
# OBJECTIVE STUDENT RESULT
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherObjectiveStudentResultDTO:
    """
    Результат одного ученика
    по одной учебной цели.
    """

    assessment_student_id: int
    student_id: int

    student_name: str

    participation_status: str
    participation_status_label: str

    score: Decimal | None
    max_score: Decimal | None
    percent: Decimal | None

    @property
    def score_display(self) -> str:
        if self.score is None:
            return "—"

        return self._format_decimal(
            self.score
        )

    @property
    def max_score_display(self) -> str:
        if self.max_score is None:
            return "—"

        return self._format_decimal(
            self.max_score
        )

    @property
    def percent_display(self) -> str:
        if self.percent is None:
            return "—"

        return (
                f"{self.percent:.2f}"
                .replace(".", ",")
                + "%"
        )

    @staticmethod
    def _format_decimal(
            value: Decimal,
    ) -> str:
        if (
                value
                == value.to_integral_value()
        ):
            return str(
                int(value)
            )

        return format(
            value.normalize(),
            "f",
        ).replace(
            ".",
            ",",
        )


# =========================================================
# OBJECTIVES PAGE
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherAssessmentObjectivesPageDTO:
    """
    Страница аналитики учебных целей
    одного Assessment для учителя.
    """

    assessment_id: int
    assessment_group_id: int

    assessment_title: str
    subject_name: str

    school_class_id: int
    class_name: str
    grade_level: int

    objectives: tuple[
        TeacherObjectiveSummaryDTO,
        ...
    ] = field(
        default_factory=tuple,
    )

    @property
    def objective_count(self) -> int:
        return len(
            self.objectives
        )


# =========================================================
# OBJECTIVE STUDENTS PAGE
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherObjectiveStudentsPageDTO:
    """
    Drill-down:
        одна учебная цель
        → результаты учеников.
    """

    assessment_id: int
    assessment_group_id: int

    assessment_title: str
    subject_name: str

    school_class_id: int
    class_name: str
    grade_level: int

    assessment_objective_id: int
    learning_objective_id: int

    objective_code: str
    objective_title: str
    objective_max_score: Decimal

    students: tuple[
        TeacherObjectiveStudentResultDTO,
        ...
    ] = field(
        default_factory=tuple,
    )

    @property
    def student_count(self) -> int:
        return len(
            self.students
        )

    @property
    def objective_max_score_display(self) -> str:
        if (
                self.objective_max_score
                == self.objective_max_score.to_integral_value()
        ):
            return str(
                int(
                    self.objective_max_score
                )
            )

        return format(
            self.objective_max_score.normalize(),
            "f",
        ).replace(
            ".",
            ",",
        )


# =========================================================
# STUDENT ANSWER REVIEW
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherStudentAnswerReviewDTO:
    """
    Один ответ ученика на странице проверки Assessment.
    """

    answer_id: int
    question_id: int

    question_type: AssessmentQuestionType
    question_text: str
    question_order_no: int

    answer_data: dict

    status: AssessmentAnswerStatus

    score: Decimal | None
    max_score: Decimal

    is_correct: bool | None

    checked_by_user_id: int | None

    question_view: dict | None = None
    response_lines: tuple[dict, ...] = ()

    @property
    def requires_manual_review(self) -> bool:
        return (
                self.status
                == AssessmentAnswerStatus.PENDING_REVIEW
        )

    @property
    def score_display(self) -> str:
        if self.score is None:
            return "—"

        return self._format_decimal(
            self.score
        )

    @property
    def max_score_display(self) -> str:
        return self._format_decimal(
            self.max_score
        )

    @staticmethod
    def _format_decimal(
            value: Decimal,
    ) -> str:
        if value == value.to_integral_value():
            return str(
                int(value)
            )

        return format(
            value.normalize(),
            "f",
        ).replace(
            ".",
            ",",
        )


@dataclass(frozen=True, slots=True)
class TeacherStudentReviewPageDTO:
    """
    Страница проверки ответов одного ученика.
    """
    assessment_id: int
    assessment_group_id: int
    assessment_student_id: int

    student_id: int
    student_name: str

    participation_status: AssessmentParticipationStatus

    result_score: Decimal | None
    result_max_score: Decimal | None
    result_percent: Decimal | None
    result_grade: AssessmentGrade | None

    answers: tuple[
        TeacherStudentAnswerReviewDTO,
        ...
    ] = field(default_factory=tuple)

    # =====================================================
    # ANSWERS
    # =====================================================

    @property
    def total_answers(self) -> int:
        return len(self.answers)

    @property
    def pending_review_count(self) -> int:
        return sum(
            1
            for answer in self.answers
            if answer.requires_manual_review
        )

    @property
    def checked_count(self) -> int:
        return sum(
            1
            for answer in self.answers
            if answer.status
            == AssessmentAnswerStatus.CHECKED
        )

    @property
    def has_pending_review(self) -> bool:
        return self.pending_review_count > 0

    # =====================================================
    # PARTICIPATION
    # =====================================================

    @property
    def participation_status_display(self) -> str:
        label = getattr(
            self.participation_status,
            "label_kz",
            None,
        )

        if label:
            return str(label)

        return self.participation_status.value

    # =====================================================
    # RESULT
    # =====================================================

    @property
    def has_result(self) -> bool:
        return (
                self.result_score is not None
                and self.result_max_score is not None
                and self.result_percent is not None
                and self.result_grade is not None
        )

    @property
    def score_display(self) -> str:
        if (
                self.result_score is None
                or self.result_max_score is None
        ):
            return "—"

        return (
            f"{self._format_decimal(self.result_score)}"
            f" / "
            f"{self._format_decimal(self.result_max_score)}"
        )

    @property
    def percent_display(self) -> str:
        if self.result_percent is None:
            return "—"

        return (
            f"{self._format_decimal(self.result_percent)}%"
        )

    @property
    def grade_display(self) -> str:
        if self.result_grade is None:
            return "—"

        return str(
            self.result_grade.value
        )

    # =====================================================
    # DISPLAY HELPERS
    # =====================================================

    @staticmethod
    def _format_decimal(
            value: Decimal,
    ) -> str:
        if value == value.to_integral_value():
            return str(
                int(value)
            )

        return (
            format(
                value.normalize(),
                "f",
            )
            .replace(".", ",")
        )
