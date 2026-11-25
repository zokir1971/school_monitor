# app/modules/assessment/schemas/knowledge_quality_export_schemas.py

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


# =========================================================
# EXPORT DETAIL ROW
# =========================================================


@dataclass(frozen=True, slots=True)
class KnowledgeQualityExportRowDTO:
    """
    Одна строка экспортной таблицы.

    В зависимости от scope:

        school
            -> класс;

        district
            -> школа;

        region
            -> район.

    Для school scope дополнительно могут
    передаваться учителя, связанные с
    AssessmentQualitySummary данного класса.

    Один класс может иметь несколько учителей,
    особенно если subject_id=None.
    """

    # =====================================================
    # ENTITY
    # =====================================================

    entity_id: int
    entity_name: str

    # =====================================================
    # TEACHERS
    # =====================================================

    teacher_names: tuple[
        str,
        ...
    ] = ()

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
    # METRICS
    # =====================================================

    average_score: Decimal | None = None
    average_percent: Decimal | None = None

    achievement_percent: Decimal | None = None
    quality_percent: Decimal | None = None

    # =====================================================
    # DISPLAY
    # =====================================================

    district_name: str = ''

    work_key: str | None = None
    full_work_title: str | None = None
    score_sum: Decimal | None = None
    percent_sum: Decimal | None = None
    work_title: str | None = None

    @property
    def teacher_names_display(self) -> str:
        """
        Отображение списка учителей
        для Excel / UI.

        Если учителей нет:
            "—"
        """

        if not self.teacher_names:
            return "—"

        return ", ".join(
            self.teacher_names
        )

# =========================================================
# EXPORT SUMMARY
# =========================================================


@dataclass(frozen=True, slots=True)
class KnowledgeQualityExportSummaryDTO:
    """
    Общий итог экспортируемой аналитики.
    """

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


# =========================================================
# EXPORT DOCUMENT
# =========================================================


@dataclass(frozen=True, slots=True)
class KnowledgeQualityExportDTO:
    """
    Унифицированные данные экспорта качества знаний.

    scope:
        school
        district
        region
    """

    scope: str

    title: str

    organization_id: int | None
    organization_name: str

    teacher_staff_member_id: int | None = None
    teacher_name: str | None = None

    academic_year_start: int | None = None

    subject_id: int | None = None
    subject_name: str | None = None

    grade_level: int | None = None

    summary: KnowledgeQualityExportSummaryDTO | None = None

    rows: tuple[
        KnowledgeQualityExportRowDTO,
        ...
    ] = field(
        default_factory=tuple,
    )

    work_summaries: tuple[KnowledgeQualityExportRowDTO, ...] = ()
    all_works: bool = False
    # Optional five-sheet regional layout; other scopes retain their old DTOs.
    school_rows: tuple[KnowledgeQualityExportRowDTO, ...] = ()
    regional_rows: tuple[KnowledgeQualityExportRowDTO, ...] = ()
    regional_work_summaries: tuple[KnowledgeQualityExportRowDTO, ...] = ()
    regional_layout: bool = False
    governance: str = ''


    work_title: str | None = None

    @property
    def academic_year_label(self) -> str:
        if self.academic_year_start is None:
            return "Барлығы"

        return (
            f"{self.academic_year_start}/"
            f"{self.academic_year_start + 1}"
        )

    @property
    def grade_level_label(self) -> str:
        if self.grade_level is None:
            return "Барлығы"

        return (
            f"{self.grade_level}-сынып"
        )

    @property
    def subject_name_display(self) -> str:
        return (
            self.subject_name
            if self.subject_name
            else "Барлық пәндер"
        )
