# app/modules/assessment/ai/question_provider.py
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.modules.assessment.schemas.ai_question_generator_dto import (
    AIQuestionGenerationRequestDTO,
    AIQuestionGenerationResponseDTO,
)


@runtime_checkable
class AIQuestionProvider(Protocol):
    """
    Абстрактный AI-провайдер генерации заданий.

    Application/service layer работает только с этим контрактом
    и не зависит от конкретного AI SDK или HTTP API.

    Провайдер:
    - получает полностью подготовленный request;
    - не обращается к БД;
    - не создаёт QuestionBankItem;
    - не управляет транзакцией;
    - не изменяет Assessment/Blueprint;
    - только генерирует структурированный ответ.
    """

    async def generate_questions(
        self,
        request: AIQuestionGenerationRequestDTO,
    ) -> AIQuestionGenerationResponseDTO:
        """
        Сгенерировать набор вопросов согласно request.
        """
        ...