# app/modules/assessment/schemas/ai_question_quality_review_dto.py
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.modules.assessment.enums import (
    AIQuestionQualityIssueSeverity,
    AIQuestionQualityVerdict,
    AssessmentLanguage,
    AssessmentQuestionDifficulty,
    AssessmentQuestionType,
)


@dataclass(slots=True, frozen=True)
class AIQuestionQualityObjectiveDTO:
    """
    Учебная цель, с которой связано проверяемое задание.

    DTO содержит готовые данные и не требует
    дополнительных запросов к БД внутри AI provider.
    """

    learning_objective_id: int
    code: str | None
    text: str


@dataclass(slots=True, frozen=True)
class AIQuestionQualityReviewRequestDTO:
    """
    Полностью сформированное задание
    для AI Quality Review.

    DTO является автономным:
        - AI provider не обращается к БД;
        - не загружает QuestionBankItem;
        - не загружает LearningObjective;
        - не изменяет исходный вопрос.

    Quality Review оценивает содержательное,
    методическое и языковое качество задания.

    Technical Question Contract должен быть проверен
    до вызова AI Quality Review.
    """

    # =====================================================
    # EDUCATION CONTEXT
    # =====================================================

    subject_id: int
    subject_name: str

    grade_level: int
    language: AssessmentLanguage

    objectives: tuple[
        AIQuestionQualityObjectiveDTO,
        ...
    ]

    # =====================================================
    # QUESTION CLASSIFICATION
    # =====================================================

    question_type: AssessmentQuestionType
    difficulty: AssessmentQuestionDifficulty

    # =====================================================
    # QUESTION CONTENT
    # =====================================================

    title: str | None
    text: str
    instruction: str | None

    content: dict[str, Any]
    answer_key: dict[str, Any]
    grading_settings: dict[str, Any]

    max_score: Decimal

    explanation: str | None = None
    text_segments: tuple[dict[str, Any], ...] = ()


@dataclass(slots=True, frozen=True)
class AIQuestionQualityReviewIssueDTO:
    """
    Одно замечание AI Quality Review.

    code:
        машинно-читаемый стабильный код проблемы.

        Примеры:
            ambiguous_question
            incorrect_answer
            weak_distractors
            objective_mismatch
            difficulty_mismatch
            language_problem

    severity:
        уровень серьёзности замечания.

    message:
        объяснение обнаруженной проблемы.

    suggestion:
        рекомендация для эксперта.

        AI не применяет suggestion автоматически
        и не изменяет исходный вопрос.
    """

    code: str

    severity: AIQuestionQualityIssueSeverity

    message: str

    suggestion: str | None = None


@dataclass(slots=True, frozen=True)
class AIQuestionQualityReviewResultDTO:
    """
    Нормализованный результат AI Quality Review.

    Результат является экспертной рекомендацией AI.

    Он:
        - не изменяет QuestionBankItem;
        - не исправляет вопрос;
        - не изменяет answer_key;
        - не изменяет QuestionBankItemStatus;
        - не переводит вопрос в READY;
        - не переводит вопрос в REJECTED.

    Окончательное решение остаётся за человеком.
    """

    verdict: AIQuestionQualityVerdict

    summary: str

    issues: tuple[
        AIQuestionQualityReviewIssueDTO,
        ...
    ] = ()

    metadata: dict[str, Any] = field(
        default_factory=dict,
    )
