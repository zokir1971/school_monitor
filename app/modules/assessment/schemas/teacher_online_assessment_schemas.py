# app/modules/assessment/schemas/teacher_online_assessment_schemas.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.modules.assessment.enums import AssessmentStatus, AssessmentParticipationStatus, AssessmentGrade


# =========================================================
# ONLINE ASSESSMENT LIST ITEM
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherOnlineAssessmentItemDTO:
    """
    Один ONLINE Assessment в рабочем кабинете учителя.
    """

    assessment_id: int

    title: str
    subject_name: str

    status: AssessmentStatus

    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None

    group_count: int
    total_students: int

    assigned_count: int
    in_progress_count: int
    submitted_count: int
    completed_count: int

    absent_count: int
    excused_count: int
    not_completed_count: int

    # -----------------------------------------------------
    # REVIEW
    # -----------------------------------------------------

    @property
    def has_pending_review(self) -> bool:
        return self.submitted_count > 0

    @property
    def pending_review_count(self) -> int:
        return self.submitted_count

    # -----------------------------------------------------
    # PROGRESS
    # -----------------------------------------------------

    @property
    def finished_count(self) -> int:
        """
        Участники, для которых выполнение уже закончено.

        SUBMITTED сюда намеренно не входит:
        работа ещё ожидает ручной проверки.
        """
        return (
            self.completed_count
            + self.absent_count
            + self.excused_count
            + self.not_completed_count
        )

    @property
    def active_count(self) -> int:
        """
        Участники, чья ONLINE-работа ещё находится
        в активном workflow.
        """
        return (
            self.assigned_count
            + self.in_progress_count
            + self.submitted_count
        )

    @property
    def completion_percent(self) -> int:
        if self.total_students <= 0:
            return 0

        percent = (
            self.finished_count
            * 100
            / self.total_students
        )

        return round(percent)

    # -----------------------------------------------------
    # DISPLAY
    # -----------------------------------------------------

    @property
    def status_display(self) -> str:
        label = getattr(
            self.status,
            "label_kz",
            None,
        )

        if label:
            return str(label)

        return self.status.value

    @property
    def subject_display(self) -> str:
        value = self.subject_name.strip()

        return value or "—"


# =========================================================
# ONLINE ASSESSMENT LIST PAGE
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherOnlineAssessmentsPageDTO:
    """
    Главная страница ONLINE Assessment учителя.
    """

    items: tuple[
        TeacherOnlineAssessmentItemDTO,
        ...
    ] = field(
        default_factory=tuple,
    )

    @property
    def total_assessments(self) -> int:
        return len(self.items)

    @property
    def total_students(self) -> int:
        return sum(
            item.total_students
            for item in self.items
        )

    @property
    def assigned_count(self) -> int:
        return sum(
            item.assigned_count
            for item in self.items
        )

    @property
    def in_progress_count(self) -> int:
        return sum(
            item.in_progress_count
            for item in self.items
        )

    @property
    def pending_review_count(self) -> int:
        return sum(
            item.submitted_count
            for item in self.items
        )

    @property
    def completed_count(self) -> int:
        return sum(
            item.completed_count
            for item in self.items
        )

    @property
    def assessments_with_pending_review_count(
        self,
    ) -> int:
        return sum(
            1
            for item in self.items
            if item.has_pending_review
        )

    @property
    def has_pending_review(self) -> bool:
        return self.pending_review_count > 0


# =========================================================
# ONLINE ASSESSMENT GROUP ITEM
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherOnlineAssessmentGroupItemDTO:
    """
    Одна группа конкретного ONLINE Assessment
    в рабочем кабинете учителя.
    """

    assessment_group_id: int
    assessment_id: int

    school_class_id: int
    class_name: str

    grade_level: int | None
    academic_year_start: int | None

    total_students: int

    assigned_count: int
    in_progress_count: int
    submitted_count: int
    completed_count: int

    absent_count: int
    excused_count: int
    not_completed_count: int

    # -----------------------------------------------------
    # REVIEW
    # -----------------------------------------------------

    @property
    def has_pending_review(self) -> bool:
        return self.submitted_count > 0

    @property
    def pending_review_count(self) -> int:
        return self.submitted_count

    # -----------------------------------------------------
    # PROGRESS
    # -----------------------------------------------------

    @property
    def finished_count(self) -> int:
        """
        Участники группы, для которых выполнение
        уже закончено.

        SUBMITTED сюда намеренно не входит:
        работа ещё ожидает ручной проверки.
        """
        return (
            self.completed_count
            + self.absent_count
            + self.excused_count
            + self.not_completed_count
        )

    @property
    def active_count(self) -> int:
        """
        Участники группы, чья ONLINE-работа
        ещё находится в активном workflow.
        """
        return (
            self.assigned_count
            + self.in_progress_count
            + self.submitted_count
        )

    @property
    def completion_percent(self) -> int:
        if self.total_students <= 0:
            return 0

        percent = (
            self.finished_count
            * 100
            / self.total_students
        )

        return round(percent)

    # -----------------------------------------------------
    # DISPLAY
    # -----------------------------------------------------

    @property
    def class_display(self) -> str:
        value = self.class_name.strip()

        return value or "—"


# =========================================================
# ONLINE ASSESSMENT GROUPS PAGE
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherOnlineAssessmentGroupsPageDTO:
    """
    Страница групп конкретного ONLINE Assessment.
    """

    assessment_id: int

    items: tuple[
        TeacherOnlineAssessmentGroupItemDTO,
        ...
    ] = field(
        default_factory=tuple,
    )

    @property
    def total_groups(self) -> int:
        return len(self.items)

    @property
    def total_students(self) -> int:
        return sum(
            item.total_students
            for item in self.items
        )

    @property
    def assigned_count(self) -> int:
        return sum(
            item.assigned_count
            for item in self.items
        )

    @property
    def in_progress_count(self) -> int:
        return sum(
            item.in_progress_count
            for item in self.items
        )

    @property
    def pending_review_count(self) -> int:
        return sum(
            item.pending_review_count
            for item in self.items
        )

    @property
    def completed_count(self) -> int:
        return sum(
            item.completed_count
            for item in self.items
        )

    @property
    def groups_with_pending_review_count(
        self,
    ) -> int:
        return sum(
            1
            for item in self.items
            if item.has_pending_review
        )

    @property
    def has_pending_review(self) -> bool:
        return self.pending_review_count > 0


# =========================================================
# ONLINE ASSESSMENT STUDENT ITEM
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherOnlineAssessmentStudentItemDTO:
    """
    Один участник группы ONLINE Assessment
    в рабочем кабинете учителя.
    """

    assessment_student_id: int
    assessment_group_id: int
    assessment_id: int

    student_id: int
    student_name: str

    participation_status: AssessmentParticipationStatus

    assigned_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None

    result_score: Decimal | None
    result_max_score: Decimal | None
    result_percent: Decimal | None
    result_grade: AssessmentGrade | None

    # -----------------------------------------------------
    # REVIEW
    # -----------------------------------------------------

    @property
    def requires_review(self) -> bool:
        return (
            self.participation_status
            == AssessmentParticipationStatus.SUBMITTED
        )

    @property
    def can_view_answers(self) -> bool:
        return self.participation_status in {
            AssessmentParticipationStatus.SUBMITTED,
            AssessmentParticipationStatus.COMPLETED,
        }

    # -----------------------------------------------------
    # RESULT
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # DISPLAY
    # -----------------------------------------------------

    @property
    def student_name_display(self) -> str:
        value = self.student_name.strip()

        return value or "—"

    # -----------------------------------------------------
    # HELPERS
    # -----------------------------------------------------

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

# =========================================================
# ONLINE ASSESSMENT STUDENTS PAGE
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherOnlineAssessmentStudentsPageDTO:
    """
    Страница участников одной группы
    ONLINE Assessment.
    """

    assessment_id: int
    assessment_group_id: int

    items: tuple[
        TeacherOnlineAssessmentStudentItemDTO,
        ...
    ] = field(
        default_factory=tuple,
    )

    @property
    def total_students(self) -> int:
        return len(self.items)

    @property
    def assigned_count(self) -> int:
        return sum(
            1
            for item in self.items
            if item.participation_status
            == AssessmentParticipationStatus.ASSIGNED
        )

    @property
    def in_progress_count(self) -> int:
        return sum(
            1
            for item in self.items
            if item.participation_status
            == AssessmentParticipationStatus.IN_PROGRESS
        )

    @property
    def pending_review_count(self) -> int:
        return sum(
            1
            for item in self.items
            if item.requires_review
        )

    @property
    def completed_count(self) -> int:
        return sum(
            1
            for item in self.items
            if item.participation_status
            == AssessmentParticipationStatus.COMPLETED
        )

    @property
    def absent_count(self) -> int:
        return sum(
            1
            for item in self.items
            if item.participation_status
            == AssessmentParticipationStatus.ABSENT
        )

    @property
    def excused_count(self) -> int:
        return sum(
            1
            for item in self.items
            if item.participation_status
            == AssessmentParticipationStatus.EXCUSED
        )

    @property
    def not_completed_count(self) -> int:
        return sum(
            1
            for item in self.items
            if item.participation_status
            == AssessmentParticipationStatus.NOT_COMPLETED
        )

    @property
    def has_pending_review(self) -> bool:
        return self.pending_review_count > 0
