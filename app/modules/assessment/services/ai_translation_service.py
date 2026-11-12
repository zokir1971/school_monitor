"""Compatibility facade. New code uses QuestionTranslationAdapter."""
from app.modules.assessment.adapters.question_translation_adapter import QuestionTranslationAdapter
from app.modules.translation.service import TranslationService

class AITranslationService(QuestionTranslationAdapter):
    def __init__(self, provider=None):
        if provider is None:
            super().__init__()
        else:
            from app.modules.assessment.ai.question_translation_provider import LegacyProviderAdapter
            super().__init__(TranslationService(LegacyProviderAdapter(provider)))
