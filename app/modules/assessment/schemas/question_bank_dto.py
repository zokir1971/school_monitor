# app/modules/assessment/schemas/question_bank_dto.py
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.modules.assessment.enums import (
    AssessmentLanguage,
    AssessmentQuestionDifficulty,
    AssessmentQuestionType,
    QuestionBankItemOrigin,
)


@dataclass(slots=True, frozen=True)
class QuestionBankObjectiveInput:
    """
    Учебная цель, с которой связано задание банка.

    order_no определяет порядок целей внутри задания.
    """

    learning_objective_id: int
    order_no: int


@dataclass(slots=True)
class QuestionBankItemCreateInput:
    """
    Данные для создания нового задания банка.

    status намеренно отсутствует:
    новое задание всегда создаётся в статусе DRAFT.
    """

    subject_id: int
    grade_level: int

    question_type: AssessmentQuestionType
    difficulty: AssessmentQuestionDifficulty
    language: AssessmentLanguage
    origin: QuestionBankItemOrigin

    text: str
    text_segments: list[dict[str, Any]]

    max_score: Decimal

    title: str | None = None
    instruction: str | None = None

    content: dict[str, Any] = field(
        default_factory=dict
    )
    answer_key: dict[str, Any] = field(
        default_factory=dict
    )
    grading_settings: dict[str, Any] = field(
        default_factory=dict
    )

    explanation: str | None = None
    author_comment: str | None = None

    objectives: list[
        QuestionBankObjectiveInput
    ] = field(
        default_factory=list
    )


@dataclass(slots=True, frozen=True)
class QuestionBankItemCreateResult:
    item_id: int
