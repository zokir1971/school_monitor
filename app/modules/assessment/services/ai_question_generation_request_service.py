# app/modules/assessment/services/ai_question_generation_request_service.py
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.ai.question_generation_request_builder import (
    AIQuestionGenerationRequestBuilder,
)
from app.modules.assessment.repositories.assessment_blueprint_repo import (
    AssessmentBlueprintRepo,
)
from app.modules.assessment.schemas.ai_question_generator_dto import (
    AIQuestionGenerationRequestDTO,
)


class AIQuestionGenerationRequestService:
    """
    Application service для подготовки запроса
    генерации вопросов из AssessmentBlueprint.

    Ответственность:

        blueprint_id
            ↓
        AssessmentBlueprint aggregate
            ↓
        AIQuestionGenerationRequestDTO

    Service:
        - читает Blueprint через repository;
        - использует aggregate query;
        - не вызывает AI provider;
        - не создаёт QuestionBankItem;
        - не выполняет commit/rollback;
        - не владеет write-транзакцией.
    """

    @classmethod
    async def build_from_blueprint(
        cls,
        db: AsyncSession,
        *,
        blueprint_id: int,
        additional_requirements: str | None = None,
    ) -> AIQuestionGenerationRequestDTO:
        if blueprint_id <= 0:
            raise ValueError(
                "blueprint_id must be positive."
            )

        blueprint = (
            await AssessmentBlueprintRepo.get_aggregate_by_id(
                db,
                blueprint_id=blueprint_id,
            )
        )

        if blueprint is None:
            raise ValueError(
                f"AssessmentBlueprint {blueprint_id} not found."
            )

        return AIQuestionGenerationRequestBuilder.build(
            blueprint=blueprint,
            additional_requirements=additional_requirements,
        )
    