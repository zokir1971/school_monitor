# app/modules/assessment/schemas/assessment_execution_schemas.py

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.modules.assessment.enums import (
    AssessmentQuestionType, AssessmentAnswerStatus,
)


@dataclass(frozen=True, slots=True)
class OnlineAssessmentQuestionDTO:
    question_id: int
    question_type: AssessmentQuestionType

    text: str
    instruction: str | None

    max_score: Decimal
    order_no: int

    content: dict[str, Any]

    is_required: bool

    # Сохранённое состояние ученика
    answer_data: dict[str, Any]
    answer_status: AssessmentAnswerStatus


@dataclass(frozen=True, slots=True)
class OnlineAssessmentPageDTO:
    assessment_id: int
    assessment_student_id: int

    title: str
    description: str | None

    subject_name: str | None

    student_name: str
    class_name: str

    duration_minutes: int | None
    remaining_seconds: int | None

    question_count: int

    questions: tuple[
        OnlineAssessmentQuestionDTO,
        ...
    ]


@dataclass(frozen=True, slots=True)
class OnlineAssessmentAnswerSaveDTO:
    answer_id: int

    question_id: int
    assessment_student_id: int

    status: str


@dataclass(frozen=True, slots=True)
class OnlineAssessmentSubmitDTO:
    assessment_id: int
    assessment_student_id: int

    participation_status: str
    completed_at: str
