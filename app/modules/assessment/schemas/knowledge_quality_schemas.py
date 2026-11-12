# app/modules/assessment/schemas/knowledge_quality_schemas.py

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


# =========================================================
# CLASS ANALYTICS
# =========================================================


@dataclass(frozen=True, slots=True)
class KnowledgeQualityClassDTO:
    """
    Аналитика качества знаний по одному классу
    внутри Assessment.
    """

    assessment_group_id: int
    school_class_id: int

    class_name: str
    grade_level: int
    academic_year_start: int

    # -----------------------------------------------------
    # PARTICIPATION
    # -----------------------------------------------------

    total_students: int

    participated_students: int

    absent_students: int
    excused_students: int
    not_completed_students: int

    # -----------------------------------------------------
    # GRADES
    # -----------------------------------------------------

    grade_5_count: int
    grade_4_count: int
    grade_3_count: int
    grade_2_count: int

    # -----------------------------------------------------
    # AVERAGES
    # -----------------------------------------------------

    average_score: Decimal | None
    average_percent: Decimal | None

    # -----------------------------------------------------
    # MAIN INDICATORS
    # -----------------------------------------------------

    achievement_percent: Decimal | None
    quality_percent: Decimal | None

    # =====================================================
    # DISPLAY
    # =====================================================

    @staticmethod
    def _percent_display(
        value: Decimal | None,
    ) -> str:
        if value is None:
            return "—"

        return (
            f"{value:.2f}"
            .replace(".", ",")
            + "%"
        )

    @staticmethod
    def _decimal_display(
        value: Decimal | None,
    ) -> str:
        if value is None:
            return "—"

        if value == value.to_integral_value():
            return str(int(value))

        return (
            f"{value:.2f}"
            .rstrip("0")
            .rstrip(".")
            .replace(".", ",")
        )

    @property
    def achievement_percent_display(self) -> str:
        return self._percent_display(
            self.achievement_percent
        )

    @property
    def quality_percent_display(self) -> str:
        return self._percent_display(
            self.quality_percent
        )

    @property
    def average_percent_display(self) -> str:
        return self._percent_display(
            self.average_percent
        )

    @property
    def average_score_display(self) -> str:
        return self._decimal_display(
            self.average_score
        )

    @property
    def participation_display(self) -> str:
        return (
            f"{self.participated_students}/"
            f"{self.total_students}"
        )


# =========================================================
# ASSESSMENT TOTAL ANALYTICS
# =========================================================


@dataclass(frozen=True, slots=True)
class KnowledgeQualityAssessmentDTO:
    """
    Итоговая аналитика по Assessment целиком.

    Может включать несколько классов одной параллели.
    """

    assessment_id: int

    title: str

    subject_id: int
    subject_name: str

    assessment_type: str
    assessment_type_label: str

    status: str
    status_label: str

    max_score: Decimal | None

    # -----------------------------------------------------
    # PARTICIPATION
    # -----------------------------------------------------

    total_students: int

    participated_students: int

    absent_students: int
    excused_students: int
    not_completed_students: int

    # -----------------------------------------------------
    # GRADES
    # -----------------------------------------------------

    grade_5_count: int
    grade_4_count: int
    grade_3_count: int
    grade_2_count: int

    # -----------------------------------------------------
    # AVERAGES
    # -----------------------------------------------------

    average_score: Decimal | None
    average_percent: Decimal | None

    # -----------------------------------------------------
    # MAIN INDICATORS
    # -----------------------------------------------------

    achievement_percent: Decimal | None
    quality_percent: Decimal | None

    # -----------------------------------------------------
    # GROUPS
    # -----------------------------------------------------

    classes: tuple[
        KnowledgeQualityClassDTO,
        ...
    ] = field(
        default_factory=tuple,
    )

    # =====================================================
    # DISPLAY
    # =====================================================

    @staticmethod
    def _percent_display(
        value: Decimal | None,
    ) -> str:
        if value is None:
            return "—"

        return (
            f"{value:.2f}"
            .replace(".", ",")
            + "%"
        )

    @staticmethod
    def _decimal_display(
        value: Decimal | None,
    ) -> str:
        if value is None:
            return "—"

        if value == value.to_integral_value():
            return str(int(value))

        return (
            f"{value:.2f}"
            .rstrip("0")
            .rstrip(".")
            .replace(".", ",")
        )

    @property
    def achievement_percent_display(self) -> str:
        return self._percent_display(
            self.achievement_percent
        )

    @property
    def quality_percent_display(self) -> str:
        return self._percent_display(
            self.quality_percent
        )

    @property
    def average_percent_display(self) -> str:
        return self._percent_display(
            self.average_percent
        )

    @property
    def average_score_display(self) -> str:
        return self._decimal_display(
            self.average_score
        )

    @property
    def max_score_display(self) -> str:
        return self._decimal_display(
            self.max_score
        )

    @property
    def participation_display(self) -> str:
        return (
            f"{self.participated_students}/"
            f"{self.total_students}"
        )

    @property
    def class_count(self) -> int:
        return len(
            self.classes
        )
