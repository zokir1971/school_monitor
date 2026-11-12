# app/modules/assessment/services/assessment_blueprint_service.py
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.schemas.assessment_blueprint_dto import (
    AssessmentBlueprintCreateInput,
    AssessmentBlueprintCreateResult,
)
from app.modules.assessment.enums import (
    AssessmentBlueprintStatus,
    AssessmentMode,
)
from app.modules.assessment.models import (
    AssessmentBlueprint,
    AssessmentBlueprintObjective,
    AssessmentBlueprintQuestionType,
    LearningObjective,
)
from app.modules.assessment.repositories.assessment_blueprint_repo import (
    AssessmentBlueprintRepo,
)


class AssessmentBlueprintService:
    """
    Бизнес-логика Assessment Blueprint.

    Service отвечает за:
        - структурную валидацию Blueprint;
        - проверку распределения типов заданий;
        - проверку распределения LearningObjective;
        - проверку принадлежности LearningObjective;
        - создание aggregate;
        - управление транзакцией.
    """

    # =====================================================
    # CREATE
    # =====================================================

    @classmethod
    async def create_blueprint(
            cls,
            db: AsyncSession,
            *,
            data: AssessmentBlueprintCreateInput,
            created_by_user_id: int | None,
    ) -> AssessmentBlueprintCreateResult:
        try:
            cls._validate_basic_fields(data)

            cls._validate_difficulty_distribution(
                data
            )

            cls._validate_question_type_distribution(
                data
            )

            cls._validate_objective_structure(
                data
            )

            if data.objectives:
                cls._validate_objective_distribution(
                    data
                )

                learning_objectives = (
                    await AssessmentBlueprintRepo
                    .get_learning_objectives_by_ids(
                        db,
                        learning_objective_ids=[
                            item.learning_objective_id
                            for item in data.objectives
                        ],
                    )
                )

                cls._validate_learning_objectives(
                    data=data,
                    learning_objectives=learning_objectives,
                )

            description = (
                data.description.strip()
                if data.description
                else None
            )

            if not description:
                description = None

            blueprint = AssessmentBlueprint(
                subject_id=data.subject_id,
                grade_level=data.grade_level,
                title=data.title.strip(),
                description=description,
                assessment_type=data.assessment_type,
                assessment_mode=data.assessment_mode,
                language=data.language,
                status=AssessmentBlueprintStatus.DRAFT,
                question_count=data.question_count,
                max_score=data.max_score,
                duration_minutes=data.duration_minutes,
                settings=dict(data.settings),
                created_by_user_id=created_by_user_id,
            )

            await AssessmentBlueprintRepo.create(
                db,
                blueprint=blueprint,
            )

            if data.objectives:
                await AssessmentBlueprintRepo.add_objectives(
                    db,
                    objectives=[
                        AssessmentBlueprintObjective(
                            blueprint_id=blueprint.id,
                            learning_objective_id=(
                                item.learning_objective_id
                            ),
                            question_count=item.question_count,
                            max_score=item.max_score,
                            order_no=item.order_no,
                        )
                        for item in data.objectives
                    ],
                )

            await AssessmentBlueprintRepo.add_question_types(
                db,
                question_types=[
                    AssessmentBlueprintQuestionType(
                        blueprint_id=blueprint.id,
                        question_type=item.question_type,
                        question_count=item.question_count,
                        max_score=item.max_score,
                        order_no=item.order_no,
                    )
                    for item in data.question_types
                ],
            )

            await db.commit()

            return AssessmentBlueprintCreateResult(
                blueprint_id=blueprint.id,
            )

        except Exception:
            await db.rollback()
            raise

    # =====================================================
    # BASIC VALIDATION
    # =====================================================

    @staticmethod
    def _validate_basic_fields(
        data: AssessmentBlueprintCreateInput,
    ) -> None:

        if not data.title.strip():
            raise ValueError(
                "Blueprint title is required."
            )

        if not 1 <= data.grade_level <= 12:
            raise ValueError(
                "grade_level must be between 1 and 12."
            )

        if data.question_count <= 0:
            raise ValueError(
                "question_count must be greater than 0."
            )

        if data.max_score <= Decimal("0"):
            raise ValueError(
                "max_score must be greater than 0."
            )

        if (
            data.duration_minutes is not None
            and data.duration_minutes <= 0
        ):
            raise ValueError(
                "duration_minutes must be greater than 0."
            )

    # =====================================================
    # QUESTION TYPE DISTRIBUTION
    # =====================================================

    @staticmethod
    def _validate_question_type_distribution(
        data: AssessmentBlueprintCreateInput,
    ) -> None:

        if not data.question_types:
            raise ValueError(
                "Blueprint must contain "
                "question type distribution."
            )

        question_types = [
            item.question_type
            for item in data.question_types
        ]

        if len(question_types) != len(
            set(question_types)
        ):
            raise ValueError(
                "Duplicate question types "
                "are not allowed."
            )

        order_numbers = [
            item.order_no
            for item in data.question_types
        ]

        if len(order_numbers) != len(
            set(order_numbers)
        ):
            raise ValueError(
                "Duplicate question type order_no "
                "is not allowed."
            )

        for item in data.question_types:
            if item.question_count <= 0:
                raise ValueError(
                    "Question type question_count "
                    "must be greater than 0."
                )

            if item.max_score <= Decimal("0"):
                raise ValueError(
                    "Question type max_score "
                    "must be greater than 0."
                )

            if item.order_no <= 0:
                raise ValueError(
                    "Question type order_no "
                    "must be greater than 0."
                )

        total_questions = sum(
            item.question_count
            for item in data.question_types
        )

        if total_questions != data.question_count:
            raise ValueError(
                "Question type question_count total "
                "must equal Blueprint question_count."
            )

        total_score = sum(
            (
                item.max_score
                for item in data.question_types
            ),
            Decimal("0"),
        )

        if total_score != data.max_score:
            raise ValueError(
                "Question type max_score total "
                "must equal Blueprint max_score."
            )

    # =====================================================
    # OBJECTIVE STRUCTURE
    # =====================================================

    @staticmethod
    def _validate_objective_structure(
        data: AssessmentBlueprintCreateInput,
    ) -> None:

        if (
            data.assessment_mode
            == AssessmentMode.WITHOUT_OBJECTIVES
        ):
            if data.objectives:
                raise ValueError(
                    "WITHOUT_OBJECTIVES Blueprint "
                    "must not contain LearningObjective."
                )

            return

        if data.assessment_mode in {
            AssessmentMode.BY_OBJECTIVES,
            AssessmentMode.ASSESSMENT_BY_SECTION,
            AssessmentMode.ASSESSMENT_BY_QUARTER,
        }:
            if not data.objectives:
                raise ValueError(
                    "This assessment mode requires "
                    "LearningObjective."
                )

            return

        raise ValueError(
            "Unsupported assessment mode: "
            f"{data.assessment_mode!r}"
        )

    # =====================================================
    # OBJECTIVE DISTRIBUTION
    # =====================================================

    @staticmethod
    def _validate_objective_distribution(
        data: AssessmentBlueprintCreateInput,
    ) -> None:

        objective_ids = [
            item.learning_objective_id
            for item in data.objectives
        ]

        if len(objective_ids) != len(
            set(objective_ids)
        ):
            raise ValueError(
                "Duplicate LearningObjective "
                "is not allowed."
            )

        order_numbers = [
            item.order_no
            for item in data.objectives
        ]

        if len(order_numbers) != len(
            set(order_numbers)
        ):
            raise ValueError(
                "Duplicate objective order_no "
                "is not allowed."
            )

        for item in data.objectives:
            if item.question_count <= 0:
                raise ValueError(
                    "Objective question_count "
                    "must be greater than 0."
                )

            if item.max_score <= Decimal("0"):
                raise ValueError(
                    "Objective max_score "
                    "must be greater than 0."
                )

            if item.order_no <= 0:
                raise ValueError(
                    "Objective order_no "
                    "must be greater than 0."
                )

        total_questions = sum(
            item.question_count
            for item in data.objectives
        )

        if total_questions != data.question_count:
            raise ValueError(
                "Objective question_count total "
                "must equal Blueprint question_count."
            )

        total_score = sum(
            (
                item.max_score
                for item in data.objectives
            ),
            Decimal("0"),
        )

        if total_score != data.max_score:
            raise ValueError(
                "Objective max_score total "
                "must equal Blueprint max_score."
            )

    # =====================================================
    # LEARNING OBJECTIVES
    # =====================================================

    @staticmethod
    def _validate_learning_objectives(
        *,
        data: AssessmentBlueprintCreateInput,
        learning_objectives: list[
            LearningObjective
        ],
    ) -> None:

        requested_ids = {
            item.learning_objective_id
            for item in data.objectives
        }

        found_by_id = {
            item.id: item
            for item in learning_objectives
        }

        missing_ids = (
            requested_ids
            - set(found_by_id)
        )

        if missing_ids:
            raise ValueError(
                "LearningObjective not found: "
                + ", ".join(
                    str(item_id)
                    for item_id in sorted(
                        missing_ids
                    )
                )
            )

        for objective_id in requested_ids:
            objective = found_by_id[
                objective_id
            ]

            if (
                objective.subject_id
                != data.subject_id
            ):
                raise ValueError(
                    "LearningObjective "
                    f"{objective.id} belongs to "
                    "another subject."
                )

            if (
                objective.grade_level
                != data.grade_level
            ):
                raise ValueError(
                    "LearningObjective "
                    f"{objective.id} belongs to "
                    "another grade level."
                )

            if not objective.is_active:
                raise ValueError(
                    "LearningObjective "
                    f"{objective.id} is inactive."
                )

    @staticmethod
    def _validate_difficulty_distribution(
            data: AssessmentBlueprintCreateInput,
    ) -> None:
        distribution = data.settings.get(
            "difficulty_distribution"
        )

        if distribution is None:
            return

        if not isinstance(distribution, dict):
            raise ValueError(
                "difficulty_distribution must be an object."
            )

        required_keys = {
            "basic",
            "medium",
            "advanced",
        }

        if set(distribution) != required_keys:
            raise ValueError(
                "difficulty_distribution must contain "
                "basic, medium and advanced."
            )

        values = []

        for key in (
                "basic",
                "medium",
                "advanced",
        ):
            value = distribution[key]

            if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
            ):
                raise ValueError(
                    f"difficulty_distribution.{key} "
                    "must be an integer."
                )

            if value < 0 or value > 100:
                raise ValueError(
                    f"difficulty_distribution.{key} "
                    "must be between 0 and 100."
                )

            values.append(value)

        if sum(values) != 100:
            raise ValueError(
                "difficulty_distribution total "
                "must equal 100."
            )
