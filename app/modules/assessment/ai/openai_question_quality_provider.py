# app/modules/assessment/ai/openai_question_quality_provider.py
from __future__ import annotations

from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)

from app.core.config import Settings, get_settings
from app.modules.assessment.ai.exceptions import AIProviderError
from app.modules.assessment.ai.question_quality_prompt_builder import (
    AIQuestionQualityPromptBuilder,
)

from app.modules.assessment.ai.question_quality_response_parser import (
    AIQuestionQualityResponseParser,
)
from app.modules.assessment.schemas.ai_question_quality_review_dto import (
    AIQuestionQualityReviewRequestDTO,
    AIQuestionQualityReviewResultDTO,
)


class OpenAIQuestionQualityProvider:
    """
    Реализация AIQuestionQualityProvider
    через OpenAI Responses API.

    OpenAI SDK изолирован внутри provider boundary.

    Provider:
    - получает полностью подготовленный request;
    - не обращается к БД;
    - не загружает QuestionBankItem;
    - не изменяет QuestionBankItem;
    - не изменяет QuestionBankItemStatus;
    - не исправляет вопрос автоматически;
    - не управляет транзакцией;
    - возвращает только структурированный
      результат AI Quality Review.

    В production клиент создаётся автоматически.

    В тестах клиент можно внедрить через constructor,
    поэтому тестирование не требует реальных API-запросов.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: Any | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client

    async def review_question(
        self,
        request: AIQuestionQualityReviewRequestDTO,
    ) -> AIQuestionQualityReviewResultDTO:
        api_key = self._require_api_key()
        model = self._require_model()

        prompt = AIQuestionQualityPromptBuilder.build(
            request
        )

        client = self._get_client(
            api_key=api_key,
        )

        try:
            response = await client.responses.create(
                model=model,
                instructions=prompt.system_prompt,
                input=prompt.user_prompt,
                text={
                    "format": {
                        "type": "json_object",
                    },
                },
                store=False,
            )

        except AuthenticationError as exc:
            raise AIProviderError(
                "AI quality review provider "
                "authentication failed.",
                code="authentication_error",
            ) from exc

        except RateLimitError as exc:
            raise AIProviderError(
                "AI quality review provider "
                "rate limit or quota exceeded.",
                code="rate_limit",
            ) from exc

        except APITimeoutError as exc:
            raise AIProviderError(
                "AI quality review provider "
                "request timed out.",
                code="timeout",
            ) from exc

        except APIConnectionError as exc:
            raise AIProviderError(
                "AI quality review provider "
                "connection failed.",
                code="connection_error",
            ) from exc

        except APIStatusError as exc:
            raise AIProviderError(
                "AI quality review provider "
                "returned an API error.",
                code="api_error",
            ) from exc

        if response.status != "completed":
            raise AIProviderError(
                f"AI response was not completed: {response.status}; "
                f"details={response.incomplete_details}",
                code="incomplete_response",
            )

        raw_output = response.output_text

        if not isinstance(raw_output, str):
            raise AIProviderError(
                "AI quality review provider response "
                "does not contain text output.",
                code="invalid_response",
            )

        raw_output = raw_output.strip()

        if not raw_output:
            raise AIProviderError(
                "AI quality review provider "
                "returned empty response.",
                code="empty_response",
            )

        try:
            result = (
                AIQuestionQualityResponseParser.parse_json(
                    raw_json=raw_output,
                )
            )

        except (ValueError, TypeError) as exc:
            raise AIProviderError(
                "AI quality review provider returned "
                "invalid structured response.",
                code="invalid_response",
            ) from exc

        return AIQuestionQualityReviewResultDTO(
            verdict=result.verdict,
            summary=result.summary,
            issues=result.issues,
            metadata={
                "provider": "openai",
                "model": model,
            },
        )

    def _get_client(
        self,
        *,
        api_key: str,
    ) -> Any:
        """
        Возвращает внедрённый клиент либо создаёт
        production-клиент.

        Создание клиента отделено от review_question(),
        чтобы provider можно было тестировать без сети.
        """

        if self._client is not None:
            return self._client

        return AsyncOpenAI(
            api_key=api_key,
            timeout=self._settings.OPENAI_TIMEOUT_SECONDS,
        )

    def _require_api_key(self) -> str:
        api_key = self._settings.openai_api_key

        if not api_key:
            raise AIProviderError(
                "AI provider API key is not configured.",
                code="configuration_error",
            )

        return api_key

    def _require_model(self) -> str:
        model = self._settings.openai_model

        if not model:
            raise AIProviderError(
                "AI provider model is not configured.",
                code="configuration_error",
            )

        return model
