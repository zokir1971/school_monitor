"""Bind labels to a question's language without changing the request/UI locale."""
from app.core.i18n import normalize_language, translate


def question_gettext(language):
    selected = normalize_language(getattr(language, 'value', language)) or 'ru'

    def gettext(message, **values):
        return translate(message, selected, **values)

    return gettext
