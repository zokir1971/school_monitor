"""Compatibility for the former assessment-specific provider interface."""
from app.modules.translation.providers.openai import OpenAITranslationProvider
from app.modules.translation.schemas import TranslationField, TranslationRequest

class QuestionTranslationProvider:
    def __init__(self, client=None, settings=None):
        self.provider = OpenAITranslationProvider(client=client, settings=settings)

    async def translate(self, fields, language, *, context=None):
        request = TranslationRequest(tuple(TranslationField(f'f{i}', text,
            path[0] == 'text_segments' and path[-1] == 'text')
            for i, (path, text) in enumerate(fields)), language, context)
        return await self.provider.translate(request)

class LegacyProviderAdapter:
    def __init__(self, provider):
        self.provider = provider

    async def translate(self, request):
        fields = [(('text_segments', i, 'text') if field.allow_empty else ('field', i), field.text)
                  for i, field in enumerate(request.fields)]
        return await self.provider.translate(fields, request.language, context=request.context)
