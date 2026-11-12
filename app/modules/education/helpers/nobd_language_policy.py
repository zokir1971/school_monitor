"""Resolve the actual class language; curriculum groups are never class languages."""
from app.modules.education.helpers.subgroup_policy import infer_language, LANGUAGES


def resolve_language(labels, selected=None, saved=None, confirmed=False):
    inferred = infer_language(labels)
    selected = selected or None
    if selected is not None and selected not in LANGUAGES:
        raise ValueError('Выберите язык обучения класса.')
    result = selected or inferred
    if result not in LANGUAGES:
        raise ValueError('Язык НОБД не определён: выберите язык класса явно.')
    if inferred is None and not confirmed:
        raise ValueError('Подтвердите выбор языка: в НОБД пустое, неизвестное или смешанное значение.')
    if inferred and result != inferred and not confirmed:
        raise ValueError('Выбранный язык отличается от НОБД. Подтвердите изменение.')
    if saved and saved != result and not confirmed:
        raise ValueError('Подтвердите изменение ранее сохранённого языка обучения.')
    return result
