# app/modules/assessment/schemas/assessment_create_schemas.py

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.modules.assessment.enums import (
    AssessmentMode,
    AssessmentType, AssessmentCheckpoint,
)


# =========================================================
# CREATE ASSESSMENT
# =========================================================


@dataclass(frozen=True, slots=True)
class AssessmentObjectiveInputDTO:
    """
    Учебная цель, выбранная при создании Assessment.

    max_score задаёт максимальный вклад этой цели
    в общий результат Assessment.
    """

    learning_objective_id: int
    max_score: Decimal
    order_no: int


@dataclass(frozen=True, slots=True)
class AssessmentCreateDTO:
    """
    Данные для создания Assessment.

    Один Assessment:
        - принадлежит одной школе;
        - относится к одному предмету;
        - может включать несколько классов;
        - может входить в AssessmentCampaign.

    assessment_mode определяет структуру работы:

        WITHOUT_OBJECTIVES
            - учебные цели не используются;

        ASSESSMENT_BY_SECTION
            - БЖБ / СОР;
            - учебные цели обязательны;

        ASSESSMENT_BY_QUARTER
            - ТЖБ / СОЧ;
            - учебные цели обязательны.

    duration_minutes:
        - для WITHOUT_OBJECTIVES может быть NULL;
        - для SECTION / QUARTER может быть указан явно;
        - если не указан, Service Layer задаёт default.

    campaign_id:
        - необязателен;
        - позволяет объединять несколько
          однопредметных Assessment в одну кампанию.
    """

    # =====================================================
    # SCOPE
    # =====================================================

    school_id: int
    subject_id: int
    created_by_user_id: int

    # =====================================================
    # CONTENT
    # =====================================================

    title: str

    school_class_ids: tuple[
        int,
        ...
    ]

    # =====================================================
    # MODE / ANALYTICS
    # =====================================================

    assessment_mode: AssessmentMode

    assessment_type: AssessmentType = (
        AssessmentType.DIAGNOSTIC
    )

    checkpoint: AssessmentCheckpoint | None = None

    # =====================================================
    # SCORING
    # =====================================================

    max_score: Decimal | None = None

    # =====================================================
    # OPTIONAL SETTINGS
    # =====================================================

    duration_minutes: int | None = None

    campaign_id: int | None = None

    description: str | None = None

    # =====================================================
    # LEARNING OBJECTIVES
    # =====================================================

    objectives: tuple[
        AssessmentObjectiveInputDTO,
        ...
    ] = field(
        default_factory=tuple,
    )

    quarter: int | None = None
    section_number: int | None = None
