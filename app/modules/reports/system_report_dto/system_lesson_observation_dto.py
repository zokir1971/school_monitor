# app/modules/reports/system_report_dto/system_lesson_observation_dto.py

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class TeacherInfoDTO:
    full_name: str
    subject: str | None
    position_text: str | None = None
    qualification_category: str | None = None


@dataclass(slots=True)
class SystemLessonObservationFillDTO:
    # =========================================================
    # ROUTE
    # =========================================================

    month_item_id: int
    selected_report_id: int

    # =========================================================
    # REPORT META
    # =========================================================

    selected_report: Any

    report_type: str
    report_code: str

    # =========================================================
    # DOCUMENT
    # =========================================================

    document: Any

    is_completed: bool
    readonly: bool

    # =========================================================
    # REPORT ENTITY
    # =========================================================

    lesson_report: Any | None

    # =========================================================
    # TEMPLATE / SCHEMA
    # =========================================================

    schema: dict

    criteria: list[dict]
    score_scale: list[int]

    max_score: int

    template_partial: str

    # =========================================================
    # RAW JSON DATA
    # =========================================================

    criteria_scores: dict

    saved_info: dict
    scores: dict
    col_sums: dict

    # =========================================================
    # HEADER INFO
    # =========================================================

    teacher_name: str
    teacher_position: str
    teacher_category: str
    subject: str

    observer_name: str
    observer_position: str

    school_name: str

    class_name: str
    group_name: str

    lesson_datetime: datetime | None

    # =========================================================
    # LESSON DATA
    # =========================================================

    theme: str
    learning_objectives: str

    lesson_objectives_1: str
    lesson_objectives_2: str
    lesson_objectives_3: str

    # =========================================================
    # RESULT
    # =========================================================

    total_score: int

    feedback: str
    suggestion_control: str
