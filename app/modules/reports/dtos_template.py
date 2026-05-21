from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class LessonObservationFormDTO:
    month_item_id: int
    selected_report_id: int
    task_execution_document_id: int | None = None

    staff_member_id: int | None = None
    observer_user_id: int | None = None

    teacher_full_name: str | None = None
    teacher_position: str | None = None
    teacher_category: str | None = None
    teacher_subject: str | None = None

    observer_full_name: str | None = None
    observer_position: str | None = None

    school_name: str | None = None
    class_name: str | None = None
    group_name: str | None = None
    lesson_datetime: datetime | None = None

    theme: str | None = None
    learning_objectives: str | None = None

    lesson_objectives_1: str | None = None
    lesson_objectives_2: str | None = None
    lesson_objectives_3: str | None = None

    lesson_plan_filename: str | None = None

    criteria_scores: dict | None = None

    col_sum_0: int | None = None
    col_sum_1: int | None = None
    col_sum_2: int | None = None
    col_sum_3: int | None = None
    total: int | None = None

    suggestion_control: str | None = None
    feedback: str | None = None


@dataclass(slots=True)
class TemplateReportListItemDTO:
    """
    DTO карточки выбранного системного отчета.

    Используется на странице списка шаблонов.
    """

    selected_report_id: int
    report_type_id: int | None
    report_code: str
    report_label: str

    target_kind: str | None = None
    target_value: str | None = None
    target_label: str | None = None

    document_id: int | None = None
    document_status: str | None = None
    is_completed: bool = False

    has_user_template: bool = False  # есть ли schema_json
    has_draft: bool = False


@dataclass(slots=True)
class TemplateReportsPageDTO:
    """
    DTO страницы системных отчетов по задаче.
    """

    month_item_id: int
    task_title: str | None
    reports: list[TemplateReportListItemDTO]


@dataclass(slots=True)
class LessonObservationInfoDTO:
    teacher_full_name: str = ""
    teacher_position: str = ""
    teacher_category: str = ""
    teacher_subject: str = ""

    observer_full_name: str = ""
    observer_position: str = ""

    school_name: str = ""
    class_name: str = ""
    group_name: str = ""

    lesson_datetime: str = ""
    theme: str = ""
    learning_objectives: str = ""

    lesson_objectives_1: str = ""
    lesson_objectives_2: str = ""
    lesson_objectives_3: str = ""

    feedback: str = ""
    suggestion_control: str = ""


@dataclass(slots=True)
class LessonObservationFillDTO:
    month_item_id: int
    selected_report_id: int

    schema: dict = field(default_factory=dict)

    report_code: str = "lesson_observation"
    report_label: str = "Сабақты бақылау парағы"

    info: LessonObservationInfoDTO = field(default_factory=LessonObservationInfoDTO)

    scores: dict = field(default_factory=dict)
    total_score: int = 0

    report: object | None = None
    document: object | None = None
