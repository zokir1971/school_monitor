# app/modules/assessment/schemas/assessment_blueprint_dto.py
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.modules.assessment.enums import (
    AssessmentLanguage,
    AssessmentMode,
    AssessmentQuestionType,
    AssessmentType,
)


@dataclass(slots=True, frozen=True)
class BlueprintObjectiveInput:
    learning_objective_id: int
    question_count: int
    max_score: Decimal
    order_no: int


@dataclass(slots=True, frozen=True)
class BlueprintQuestionTypeInput:
    question_type: AssessmentQuestionType
    question_count: int
    max_score: Decimal
    order_no: int


@dataclass(slots=True)
class AssessmentBlueprintCreateInput:
    subject_id: int
    grade_level: int

    title: str
    description: str | None

    assessment_type: AssessmentType
    assessment_mode: AssessmentMode
    language: AssessmentLanguage

    question_count: int
    max_score: Decimal
    duration_minutes: int | None = None

    settings: dict[str, Any] = field(
        default_factory=dict
    )

    objectives: list[
        BlueprintObjectiveInput
    ] = field(
        default_factory=list
    )

    question_types: list[
        BlueprintQuestionTypeInput
    ] = field(
        default_factory=list
    )


@dataclass(slots=True, frozen=True)
class AssessmentBlueprintCreateResult:
    blueprint_id: int
    