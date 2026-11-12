# app/modules/assessment/services/ai_question_quality_review_service.py
from __future__ import annotations

from app.modules.assessment.helpers.ai_question_contract import normalize_text_segments, validate_review_contract

from app.modules.assessment.ai.question_quality_provider import (
    AIQuestionQualityProvider,
)
from app.modules.assessment.schemas.ai_question_quality_review_dto import (
    AIQuestionQualityReviewRequestDTO,
    AIQuestionQualityReviewResultDTO,
)
from app.modules.assessment.services.assessment_question_validation_service import (
    AssessmentQuestionValidationService,
)


class AIQuestionQualityReviewService:
    """
    Application service для AI Quality Review одного задания.

    Отвечает за orchestration:

        Quality Review Request
                ↓
        Technical Validation
                ↓
        AIQuestionQualityProvider
                ↓
        Quality Review Result

    Сервис:
    - не работает с БД;
    - не использует repository;
    - не загружает QuestionBankItem;
    - не изменяет QuestionBankItem;
    - не изменяет QuestionBankItemStatus;
    - не управляет транзакцией;
    - не зависит от конкретного AI SDK;
    - не исправляет вопрос автоматически.

    Provider вызывается только после успешной
    технической проверки Question Contract.

    AI verdict является рекомендацией.
    Финальное решение принимает человек.
    """

    def __init__(
        self,
        *,
        provider: AIQuestionQualityProvider,
    ) -> None:
        self._provider = provider

    async def review(
        self,
        request: AIQuestionQualityReviewRequestDTO,
    ) -> AIQuestionQualityReviewResultDTO:
        """
        Выполнить AI Quality Review одного вопроса.

        Перед обращением к AI обязательно выполняется
        техническая проверка Question Contract.

        Если technical validation завершается ошибкой,
        provider не вызывается.
        """

        self._validate_question_contract(request)

        return await self._provider.review_question(
            request
        )

    # ============================================================
    # TECHNICAL VALIDATION
    # ============================================================

    @staticmethod
    def _validate_question_contract(
        request: AIQuestionQualityReviewRequestDTO,
    ) -> None:
        """
        Проверяет техническую структуру вопроса.

        Здесь намеренно используется существующий
        AssessmentQuestionValidationService.

        Quality Review не должен получать технически
        некорректный Question Contract.
        """

        try:
            AssessmentQuestionValidationService.validate(
                question_type=request.question_type,
                content=request.content,
                answer_key=request.answer_key,
                grading_settings=request.grading_settings,
            )

            normalize_text_segments(request.text, request.text_segments, allow_images=True)
            validate_review_contract(question_type=request.question_type,
                                    grading_settings=request.grading_settings, max_score=request.max_score)

        except ValueError as exc:
            raise ValueError(
                "Question не прошёл technical validation "
                "перед AI Quality Review: "
                f"{exc}"
            ) from exc
