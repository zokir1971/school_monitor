"""Read-only, language-specific template hints for both annual-plan forms."""
from app.core.i18n import normalize_language
from app.modules.planning.content_i18n import content_text,loaded,language
from app.modules.planning.enums import ReviewPlace
from app.modules.planning.review_places import legacy_places


def _place_labels(value,lang):
    places=legacy_places(value)
    if not places:return ''
    return ', '.join(place.display_label(lang)for place in ReviewPlace if place.value in places)


def sample_text(row,field,lang=None):
    """Use an authored translation, or render a known place from enum metadata.

    Missing translations of arbitrary prose stay empty. No authored values,
    selected places, source fingerprints or ORM relationships are changed.
    """
    if row is None:return ''
    lang=normalize_language(lang)or language()
    value=str(content_text(row,field,lang)or'').strip()
    if field!='review_place':return value
    if value:
        return _place_labels(value,lang)or value
    data=loaded(row,'text_i18n')or{}
    raw=loaded(row,field)
    baseline=data.get('_base',{})
    stale=field in baseline and baseline[field]!=raw
    # Respect a deliberately blank language field. A changed source invalidates
    # its previous translations; only its current recognized place can be shown.
    if not stale and field in data.get(lang,{}):return ''
    return _place_labels(raw,lang)
