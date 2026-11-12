from app.modules.translation.schemas import TranslationRequest
from app.modules.translation.providers.base import TranslationProvider
from app.modules.translation.helpers.text_validation import validate_request, validate_result

class TranslationService:
    def __init__(self, provider: TranslationProvider | None = None):
        self.provider = provider

    async def translate(self, request: TranslationRequest) -> dict[str, str]:
        validate_request(request)
        provider = self.provider
        if provider is None:
            from app.modules.translation.providers.openai import OpenAITranslationProvider
            provider = OpenAITranslationProvider()
        result = await provider.translate(request)
        return validate_result(request, result)
