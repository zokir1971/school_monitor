# app/modules/assessment/ai/openai_question_provider.py
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
from app.modules.assessment.ai.question_prompt_builder import (
    AIQuestionPromptBuilder,
)
from app.modules.assessment.ai.question_response_parser import (
    AIQuestionResponseParser,
)
from app.modules.assessment.schemas.ai_question_generator_dto import (
    AIQuestionGenerationRequestDTO,
    AIQuestionGenerationResponseDTO,
)


class OpenAIQuestionProvider:
    """
    Реализация AIQuestionProvider через OpenAI Responses API.

    OpenAI SDK изолирован внутри provider boundary.

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

    async def generate_questions(
        self,
        request: AIQuestionGenerationRequestDTO,
    ) -> AIQuestionGenerationResponseDTO:
        self.last_generation_output = None
        self.last_response_metadata = {}
        api_key = self._require_api_key()
        model = self._require_model()

        prompt = self._build_prompt(request)
        from app.modules.assessment.helpers.ai_source_image import vision_input, IMAGE_INSTRUCTION
        image_data = getattr(self, 'source_image_data_url', None)
        option_data = getattr(self, 'image_option_data_urls', ())
        if getattr(request, 'image_option_keys', ()) and len(option_data) != 4:
            raise ValueError('Four option image inputs are missing.')
        if getattr(request, 'source_image_key', None) and not image_data:
            raise ValueError('Source image data is missing; select the image again.')
        input_text = "Return the result as a valid JSON object only. Do not use Markdown code fences.\n\n" + prompt.user_prompt
        if image_data:
            input_text += IMAGE_INSTRUCTION
        if option_data:
            from app.modules.assessment.helpers.ai_source_image import IMAGE_OPTIONS_INSTRUCTION
            input_text += IMAGE_OPTIONS_INSTRUCTION

        client = self._get_client(
            api_key=api_key,
        )

        try:
            response = await client.responses.create(
                model=model,
                instructions=prompt.system_prompt,
                input=vision_input(input_text, image_data, option_data),
                text={"format": {"type": "json_object"}},
                store=False,
            )

        except AuthenticationError as exc:
            raise AIProviderError(
                "AI provider authentication failed.",
                code="authentication_error",
            ) from exc

        except RateLimitError as exc:
            raise AIProviderError(
                "AI provider rate limit or quota exceeded.",
                code="rate_limit",
            ) from exc

        except APITimeoutError as exc:
            raise AIProviderError(
                "AI provider request timed out.",
                code="timeout",
            ) from exc

        except APIConnectionError as exc:
            raise AIProviderError(
                "AI provider connection failed.",
                code="connection_error",
            ) from exc

        except APIStatusError as exc:
            raise AIProviderError(
                "AI provider returned an API error.",
                code="api_error",
            ) from exc

        from app.modules.assessment.helpers.generation_response_diagnostics import response_metadata
        self.last_response_metadata = response_metadata(response)

        # Do not parse a partial JSON document as a completed answer.
        status = getattr(response, "status", None)
        if status != "completed":
            details = getattr(response, "incomplete_details", None)
            reason = getattr(details, "reason", None)
            error = AIProviderError(
                f"AI provider response was not completed: status={status!r}, reason={reason!r}.",
                code="incomplete_response" if status == "incomplete" else "invalid_response",
            )
            # Preserve evidence, but never parse/save a partial document as a valid task.
            raw = getattr(response, 'output_text', None)
            if isinstance(raw, str):
                import logging
                from app.modules.assessment.helpers.bilingual_failure_diagnostics import save_failure
                try:
                    path = save_failure(raw, request, error, response_metadata=self.last_response_metadata)
                    logging.getLogger(__name__).error('Incomplete AI response diagnostic: %s', path)
                except Exception:
                    logging.getLogger(__name__).error('Could not save incomplete AI response diagnostic.')
            raise error

        for output_item in getattr(response, "output", None) or []:
            for part in getattr(output_item, "content", None) or []:
                if getattr(part, "type", None) == "refusal":
                    raise AIProviderError(
                        "AI provider declined the generation request.",
                        code="refusal",
                    )

        raw_output = response.output_text

        if not isinstance(raw_output, str):
            raise AIProviderError(
                "AI provider response does not contain text output.",
                code="invalid_response",
            )

        raw_output = raw_output.strip()

        if not raw_output:
            raise AIProviderError(
                "AI provider returned empty response.",
                code="empty_response",
            )

        try:
            return self._parse_response(raw_output, request)
        except (ValueError, TypeError) as exc:
            raise AIProviderError(
                "AI provider returned invalid structured response.",
                code="invalid_response",
            ) from exc

    def _build_prompt(self, request):
        return AIQuestionPromptBuilder.build(request)

    def _parse_response(self, raw_output, request):
        return AIQuestionResponseParser.parse_json(raw_json=raw_output, request=request)

    def _get_client(
        self,
        *,
        api_key: str,
    ) -> Any:
        """
        Возвращает внедрённый клиент либо создаёт production-клиент.

        Создание клиента отделено от generate_questions(),
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
