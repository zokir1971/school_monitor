# app/modules/assessment/schemas/knowledge_quality_analytics_schemas.py

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class KnowledgeQualityAnalyticsDTO:
    """
    Унифицированный результат аналитики качества знаний.

    Используется для:
        - школы;
        - района;
        - региона.

    Расчётные показатели формируются через
    KnowledgeQualityCalculator.
    """

    scope: str

    school_id: int | None = None
    district_id: int | None = None
    region_id: int | None = None

    academic_year_start: int | None = None
    subject_id: int | None = None
    grade_level: int | None = None

    # =====================================================
    # PARTICIPATION
    # =====================================================

    total_students: int = 0
    participated_students: int = 0

    absent_students: int = 0
    excused_students: int = 0
    not_completed_students: int = 0

    # =====================================================
    # GRADES
    # =====================================================

    grade_5_count: int = 0
    grade_4_count: int = 0
    grade_3_count: int = 0
    grade_2_count: int = 0

    # =====================================================
    # AGGREGATES
    # =====================================================

    score_sum: Decimal = Decimal("0")
    percent_sum: Decimal = Decimal("0")

    # =====================================================
    # CALCULATED METRICS
    # =====================================================

    average_score: Decimal | None = None
    average_percent: Decimal | None = None

    achievement_percent: Decimal | None = None
    quality_percent: Decimal | None = None

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
            return str(
                int(value)
            )

        return (
            f"{value:.2f}"
            .rstrip("0")
            .rstrip(".")
            .replace(".", ",")
        )

    @property
    def average_score_display(self) -> str:
        return self._decimal_display(
            self.average_score
        )

    @property
    def average_percent_display(self) -> str:
        return self._percent_display(
            self.average_percent
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
    def participation_display(self) -> str:
        return (
            f"{self.participated_students}/"
            f"{self.total_students}"
        )


@dataclass(frozen=True, slots=True)
class KnowledgeQualityDrillDownItemDTO:
    """
    Одна строка drill-down аналитики.

    entity_id:
        school_id   — для district -> schools;
        district_id — для region -> districts.
    """

    entity_id: int
    entity_name: str

    total_students: int
    participated_students: int

    absent_students: int
    excused_students: int
    not_completed_students: int

    grade_5_count: int
    grade_4_count: int
    grade_3_count: int
    grade_2_count: int

    score_sum: Decimal
    percent_sum: Decimal

    average_score: Decimal | None
    average_percent: Decimal | None

    achievement_percent: Decimal | None
    quality_percent: Decimal | None

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
            return str(
                int(value)
            )

        return (
            f"{value:.2f}"
            .rstrip("0")
            .rstrip(".")
            .replace(".", ",")
        )

    @property
    def participation_display(self) -> str:
        return (
            f"{self.participated_students}/"
            f"{self.total_students}"
        )

    @property
    def average_score_display(self) -> str:
        return self._decimal_display(
            self.average_score
        )

    @property
    def average_percent_display(self) -> str:
        return self._percent_display(
            self.average_percent
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


@dataclass(frozen=True, slots=True)
class KnowledgeQualityDrillDownDTO:
    """
    Набор строк drill-down аналитики.

    scope:
        district_schools
        region_districts
    """

    scope: str

    parent_id: int

    academic_year_start: int | None = None
    subject_id: int | None = None
    grade_level: int | None = None

    items: tuple[
        KnowledgeQualityDrillDownItemDTO,
        ...
    ] = ()

    @property
    def item_count(self) -> int:
        return len(
            self.items
        )


@dataclass(frozen=True, slots=True)
class KnowledgeQualityDrillDownItemDTO:
    """
    Одна строка drill-down аналитики.

    entity_id:
        school_id   — district -> schools
        district_id — region -> districts
    """

    entity_id: int
    entity_name: str

    total_students: int
    participated_students: int

    absent_students: int
    excused_students: int
    not_completed_students: int

    grade_5_count: int
    grade_4_count: int
    grade_3_count: int
    grade_2_count: int

    score_sum: Decimal
    percent_sum: Decimal

    average_score: Decimal | None
    average_percent: Decimal | None

    achievement_percent: Decimal | None
    quality_percent: Decimal | None

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
            return str(
                int(value)
            )

        return (
            f"{value:.2f}"
            .rstrip("0")
            .rstrip(".")
            .replace(".", ",")
        )

    @property
    def participation_display(self) -> str:
        return (
            f"{self.participated_students}/"
            f"{self.total_students}"
        )

    @property
    def average_score_display(self) -> str:
        return self._decimal_display(
            self.average_score
        )

    @property
    def average_percent_display(self) -> str:
        return self._percent_display(
            self.average_percent
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


@dataclass(frozen=True, slots=True)
class KnowledgeQualityDrillDownDTO:
    """
    Drill-down одного организационного уровня.
    """

    scope: str
    parent_id: int

    academic_year_start: int | None = None
    subject_id: int | None = None
    grade_level: int | None = None

    items: tuple[
        KnowledgeQualityDrillDownItemDTO,
        ...
    ] = ()

    @property
    def item_count(self) -> int:
        return len(
            self.items
        )


@dataclass(frozen=True, slots=True)
class KnowledgeQualitySchoolClassItemDTO:
    school_class_id: int
    class_name: str
    grade_level: int

    total_students: int
    participated_students: int

    absent_students: int
    excused_students: int
    not_completed_students: int

    grade_5_count: int
    grade_4_count: int
    grade_3_count: int
    grade_2_count: int

    average_score: Decimal | None
    average_percent: Decimal | None

    achievement_percent: Decimal | None
    quality_percent: Decimal | None

    @property
    def participation_display(self) -> str:
        return (
            f"{self.participated_students}/"
            f"{self.total_students}"
        )

    @property
    def average_score_display(self) -> str:
        if self.average_score is None:
            return "—"

        value = self.average_score.quantize(
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

    @property
    def average_percent_display(self) -> str:
        return self._percent_display(
            self.average_percent
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

    @staticmethod
    def _percent_display(
            value: Decimal | None,
    ) -> str:
        if value is None:
            return "—"

        return (
                format(
                    value.quantize(
                        Decimal("0.01")
                    ),
                    ".2f",
                ).replace(
                    ".",
                    ",",
                )
                + "%"
        )


@dataclass(frozen=True, slots=True)
class KnowledgeQualitySchoolClassesDTO:
    school_id: int

    academic_year_start: int | None = None
    subject_id: int | None = None
    grade_level: int | None = None

    items: tuple[
        KnowledgeQualitySchoolClassItemDTO,
        ...
    ] = ()

    @property
    def item_count(self) -> int:
        return len(
            self.items
        )
