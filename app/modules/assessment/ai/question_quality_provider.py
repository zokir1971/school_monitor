# app/modules/assessment/ai/question_quality_provider.py
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.modules.assessment.schemas.ai_question_quality_review_dto import (
    AIQuestionQualityReviewRequestDTO,
    AIQuestionQualityReviewResultDTO,
)


@runtime_checkable
class AIQuestionQualityProvider(Protocol):
    """
    Абстрактный AI-провайдер проверки качества задания.

    Application/service layer работает только
    с этим контрактом и не зависит от конкретного
    AI SDK или HTTP API.

    Провайдер:
    - получает полностью подготовленный request;
    - не обращается к БД;
    - не загружает QuestionBankItem;
    - не изменяет QuestionBankItem;
    - не изменяет QuestionBankItemStatus;
    - не исправляет вопрос автоматически;
    - не управляет транзакцией;
    - только выполняет AI Quality Review
      и возвращает структурированный результат.

    AI verdict является рекомендацией.

    PASS не означает автоматический READY.
    REJECT не означает автоматический REJECTED.

    Финальное решение принимает человек.
    """

    async def review_question(
        self,
        request: AIQuestionQualityReviewRequestDTO,
    ) -> AIQuestionQualityReviewResultDTO:
        """
        Выполнить AI Quality Review одного задания.
        """
        ...
