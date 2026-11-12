# app/modules/assessment/ai/question_generation_request_builder.py
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.modules.assessment.enums import AssessmentLanguage
from app.modules.assessment.models import (
    AssessmentBlueprint,
    AssessmentBlueprintObjective,
)
from app.modules.assessment.schemas.ai_question_generator_dto import (
    AIQuestionGenerationDifficultyDTO,
    AIQuestionGenerationObjectiveDTO,
    AIQuestionGenerationRequestDTO,
    AIQuestionGenerationTypeDTO,
)


class AIQuestionGenerationRequestBuilder:
    """
    Преобразует загруженный AssessmentBlueprint aggregate
    в AIQuestionGenerationRequestDTO.

    Builder является чистым application/domain mapper:

        AssessmentBlueprint aggregate
            ->
        AIQuestionGenerationRequestDTO

    Builder:
        - не работает с БД;
        - не вызывает repository;
        - не вызывает AI provider;
        - не управляет транзакциями;
        - не выполняет lazy loading.

    Relationships Blueprint должны быть явно доступны
    вызывающему коду до вызова build().
    """

    @classmethod
    def build(
        cls,
        *,
        blueprint: AssessmentBlueprint,
        additional_requirements: str | None = None,
    ) -> AIQuestionGenerationRequestDTO:
        cls._validate_blueprint(
            blueprint=blueprint,
        )

        objectives = tuple(
            cls._build_objective(
                blueprint=blueprint,
                blueprint_objective=objective,
            )
            for objective in blueprint.objectives
        )

        question_types = tuple(
            AIQuestionGenerationTypeDTO(
                question_type=item.question_type,
                question_count=item.question_count,
                max_score=item.max_score,
            )
            for item in blueprint.question_types
        )

        difficulty = cls._build_difficulty(
            settings=blueprint.settings,
        )

        return AIQuestionGenerationRequestDTO(
            blueprint_id=blueprint.id,
            subject_id=blueprint.subject_id,
            subject_name=cls._get_subject_name(
                blueprint=blueprint,
            ),
            grade_level=blueprint.grade_level,
            language=blueprint.language,
            assessment_title=blueprint.title.strip(),
            question_count=blueprint.question_count,
            max_score=blueprint.max_score,
            objectives=objectives,
            question_types=question_types,
            difficulty=difficulty,
            additional_requirements=(
                cls._normalize_optional_text(
                    additional_requirements
                )
            ),
        )

    # =========================================================
    # OBJECTIVES
    # =========================================================

    @classmethod
    def _build_objective(
        cls,
        *,
        blueprint: AssessmentBlueprint,
        blueprint_objective: AssessmentBlueprintObjective,
    ) -> AIQuestionGenerationObjectiveDTO:
        learning_objective = (
            blueprint_objective.learning_objective
        )

        objective_text = cls._get_learning_objective_text(
            language=blueprint.language,
            learning_objective=learning_objective,
        )

        return AIQuestionGenerationObjectiveDTO(
            learning_objective_id=(
                blueprint_objective.learning_objective_id
            ),
            code=learning_objective.code,
            text=objective_text,
            question_count=blueprint_objective.question_count,
            max_score=blueprint_objective.max_score,
        )

    @staticmethod
    def _get_learning_objective_text(
        *,
        language: AssessmentLanguage,
        learning_objective: Any,
    ) -> str:
        if language == AssessmentLanguage.KAZAKH:
            value = learning_objective.title_kz

        elif language == AssessmentLanguage.RUSSIAN:
            value = learning_objective.title_ru

        elif language == AssessmentLanguage.ENGLISH:
            raise ValueError(
                "English LearningObjective text is not supported: "
                "LearningObjective has no title_en field."
            )

        else:
            raise ValueError(
                f"Unsupported assessment language: {language!r}."
            )

        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "LearningObjective does not contain text "
                f"for language {language.value!r}. "
                f"learning_objective_id={learning_objective.id}."
            )

        return value.strip()

    # =========================================================
    # SUBJECT
    # =========================================================

    @staticmethod
    def _get_subject_name(
        *,
        blueprint: AssessmentBlueprint,
    ) -> str:
        subject = blueprint.subject

        if blueprint.language == AssessmentLanguage.KAZAKH:
            value = subject.name_kz

        elif blueprint.language == AssessmentLanguage.RUSSIAN:
            value = subject.name_ru

        elif blueprint.language == AssessmentLanguage.ENGLISH:
            raise ValueError(
                "English Subject name is not supported: "
                "Subject has no name_en field."
            )

        else:
            raise ValueError(
                "Unsupported assessment language: "
                f"{blueprint.language!r}."
            )

        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "Subject does not contain a name "
                f"for language {blueprint.language.value!r}. "
                f"subject_id={blueprint.subject_id}."
            )

        return value.strip()

    # =========================================================
    # DIFFICULTY
    # =========================================================

    @classmethod
    def _build_difficulty(
        cls,
        *,
        settings: dict[str, Any],
    ) -> AIQuestionGenerationDifficultyDTO | None:
        raw_distribution = settings.get(
            "difficulty_distribution"
        )

        if raw_distribution is None:
            return None

        if not isinstance(raw_distribution, dict):
            raise ValueError(
                "Blueprint difficulty_distribution "
                "must be an object."
            )

        expected_keys = {
            "basic",
            "medium",
            "advanced",
        }

        if set(raw_distribution) != expected_keys:
            raise ValueError(
                "Blueprint difficulty_distribution must contain "
                "exactly: basic, medium, advanced."
            )

        basic = cls._validate_percentage(
            raw_distribution["basic"],
            field_name="basic",
        )

        medium = cls._validate_percentage(
            raw_distribution["medium"],
            field_name="medium",
        )

        advanced = cls._validate_percentage(
            raw_distribution["advanced"],
            field_name="advanced",
        )

        if basic + medium + advanced != 100:
            raise ValueError(
                "Blueprint difficulty_distribution "
                "must total exactly 100."
            )

        return AIQuestionGenerationDifficultyDTO(
            basic=basic,
            medium=medium,
            advanced=advanced,
        )

    @staticmethod
    def _validate_percentage(
        value: Any,
        *,
        field_name: str,
    ) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                "Blueprint difficulty percentage "
                f"{field_name!r} must be an integer."
            )

        if value < 0 or value > 100:
            raise ValueError(
                "Blueprint difficulty percentage "
                f"{field_name!r} must be between 0 and 100."
            )

        return value

    # =========================================================
    # BLUEPRINT VALIDATION
    # =========================================================

    @staticmethod
    def _validate_blueprint(
        *,
        blueprint: AssessmentBlueprint,
    ) -> None:
        if blueprint.id is None:
            raise ValueError(
                "AssessmentBlueprint must be persisted "
                "before AI generation."
            )

        if blueprint.subject_id <= 0:
            raise ValueError(
                "AssessmentBlueprint subject_id must be positive."
            )

        if not 1 <= blueprint.grade_level <= 12:
            raise ValueError(
                "AssessmentBlueprint grade_level "
                "must be between 1 and 12."
            )

        if (
            not isinstance(blueprint.title, str)
            or not blueprint.title.strip()
        ):
            raise ValueError(
                "AssessmentBlueprint title must not be empty."
            )

        if blueprint.question_count <= 0:
            raise ValueError(
                "AssessmentBlueprint question_count "
                "must be positive."
            )

        if not isinstance(blueprint.max_score, Decimal):
            raise ValueError(
                "AssessmentBlueprint max_score must be Decimal."
            )

        if blueprint.max_score <= Decimal("0"):
            raise ValueError(
                "AssessmentBlueprint max_score must be positive."
            )

        if not isinstance(blueprint.settings, dict):
            raise ValueError(
                "AssessmentBlueprint settings must be an object."
            )

        if not blueprint.question_types:
            raise ValueError(
                "AssessmentBlueprint must contain "
                "question type distribution."
            )

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _normalize_optional_text(
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        return normalized or None
