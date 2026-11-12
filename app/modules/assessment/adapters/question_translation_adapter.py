"""Assessment protection and field mapping stay in the assessment module."""
from app.modules.assessment.helpers.bilingual_question_contract import (
    translation_fields, make_variant, assert_variant_contract)
from app.modules.translation.schemas import TranslationField, TranslationRequest
from app.modules.translation.service import TranslationService

class QuestionTranslationAdapter:
    def __init__(self, service=None):
        self.service = service or TranslationService()

    async def translate_question(self, payload, question_type, language):
        fields = translation_fields(payload, question_type)
        request = TranslationRequest(
            fields=tuple(TranslationField(f'f{i}', text,
                path[0] == 'text_segments' and path[-1] == 'text')
                for i, (path, text) in enumerate(fields)),
            language=language, context=payload)
        values = await self.service.translate(request)
        translated = make_variant(payload, question_type, values)
        assert_variant_contract(payload, translated, question_type)
        return values, translated
