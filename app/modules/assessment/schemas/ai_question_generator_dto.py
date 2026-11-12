# app/modules/assessment/schemas/ai_question_generator_dto.py
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.modules.assessment.enums import (
    AssessmentLanguage,
    AssessmentQuestionDifficulty,
    AssessmentQuestionType,
)


@dataclass(slots=True, frozen=True)
class AIQuestionGenerationObjectiveDTO:
    """
    Учебная цель, для которой AI должен создать задания.
    """

    learning_objective_id: int
    code: str | None
    text: str

    question_count: int
    max_score: Decimal


@dataclass(slots=True, frozen=True)
class AIQuestionGenerationTypeDTO:
    """
    Требуемое количество заданий определённого типа.
    """

    question_type: AssessmentQuestionType
    question_count: int
    max_score: Decimal


@dataclass(slots=True, frozen=True)
class AIQuestionGenerationDifficultyDTO:
    """
    Распределение сложности в процентах.
    """

    basic: int
    medium: int
    advanced: int


@dataclass(slots=True, frozen=True)
class AIQuestionGenerationRequestDTO:
    """
    Полностью сформированное техническое задание для AI.

    Этот DTO уже не должен требовать дополнительных запросов
    к БД внутри AI provider.
    """

    blueprint_id: int | None

    subject_id: int
    subject_name: str

    grade_level: int
    language: AssessmentLanguage

    assessment_title: str

    question_count: int
    max_score: Decimal

    objectives: tuple[
        AIQuestionGenerationObjectiveDTO,
        ...
    ]

    question_types: tuple[
        AIQuestionGenerationTypeDTO,
        ...
    ]

    difficulty: (
        AIQuestionGenerationDifficultyDTO | None
    )

    additional_requirements: str | None = None
    creation_plan: tuple[dict, ...] = ()
    source_image_key: str | None = None
    image_option_keys: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class AIGeneratedQuestionDTO:
    """
    Один вопрос, полученный от AI.

    Формат намеренно совпадает с нашим Question Contract.
    """

    question_type: AssessmentQuestionType

    title: str | None
    text: str
    instruction: str | None

    content: dict[str, Any]
    answer_key: dict[str, Any]
    grading_settings: dict[str, Any]

    difficulty: AssessmentQuestionDifficulty
    max_score: Decimal

    learning_objective_ids: tuple[int, ...] = ()

    explanation: str | None = None
    text_segments: tuple[dict[str, Any], ...] = ()


@dataclass(slots=True, frozen=True)
class AIQuestionGenerationResponseDTO:
    """
    Нормализованный результат одного вызова AI generator.
    """

    questions: tuple[
        AIGeneratedQuestionDTO,
        ...
    ]

    warnings: tuple[str, ...] = ()

    metadata: dict[str, Any] = field(
        default_factory=dict,
    )
    