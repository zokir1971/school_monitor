from app.modules.planning.content_i18n import content_text
"""Display persisted planning/execution fields without lazy database reads."""
from collections.abc import Mapping
from app.modules.planning.enums import ControlForm, ReviewPlace

CONTROL_FORMS_RU = {
    'personal': 'Персональный контроль',
    'class_generalizing': 'Классно-обобщающий контроль',
    'subject_generalizing': 'Предметно-обобщающий контроль',
    'thematic_generalizing': 'Тематически-обобщающий контроль',
    'overview': 'Обзорный контроль',
    'complex_generalizing': 'Комплексно-обобщающий контроль',
}
REVIEW_PLACES_RU = {place.value:place.label_ru for place in ReviewPlace}

def loaded(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    state = getattr(obj, '__dict__', None)
    if isinstance(state, dict):
        return state.get(name, default)
    return getattr(obj, name, default)

def text(value):
    return str(getattr(value, 'value', value) or '').strip()

def enum_label(value, enum, ru_labels, language):
    if enum is ReviewPlace:
        from app.modules.planning.review_places import parse_place
        place = parse_place(value)
        if place is not None:
            return place.display_label(language)
    raw = text(value)
    if not raw:
        return ''
    member = next((e for e in enum if raw in (e.value, e.label_kz)), None)
    if member is None:
        return raw
    return ru_labels.get(member.value, member.label_kz) if language == 'ru' else member.label_kz

def review_place_text(task, language='kk'):
    source = loaded(task, 'source_row11')
    # Preserve the saved monthly snapshot; fall back for older plans only.
    for rows in (loaded(task, 'review_places') or [], loaded(source, 'review_places') or []):
        labels = []
        for row in rows:
            label = enum_label(loaded(row, 'review_place'), ReviewPlace, REVIEW_PLACES_RU, language)
            if label and label not in labels:
                labels.append(label)
        if labels:
            return ', '.join(labels)
    legacy = text(content_text(source, 'review_place', language))
    if not legacy:
        legacy = text(loaded(loaded(task, 'execution'), 'planned_review_place'))
    return enum_label(legacy, ReviewPlace, REVIEW_PLACES_RU, language) or '—'

def execution_fields(task, execution_data=None):
    source = loaded(task, 'source_row11')
    raw = text(loaded(execution_data, 'control_form'))
    if not raw:
        raw = text(loaded(loaded(task, 'execution'), 'control_form'))
    return dict(
        control_methods=text(content_text(source, 'methods')) or '—',
        control_form=enum_label(raw, ControlForm, CONTROL_FORMS_RU, 'kk') or '—',
        control_form_ru=enum_label(raw, ControlForm, CONTROL_FORMS_RU, 'ru') or '—',
        review_place=review_place_text(task, 'kk'),
        review_place_ru=review_place_text(task, 'ru'),
    )
