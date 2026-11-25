"""One source of review-place labels and confirmed legacy spellings.

Only immutable enum metadata is cached. Place codes and authorization rules are
independent of the selected UI language; authored text is never translated here.
"""
from functools import lru_cache
import re,unicodedata
from app.modules.planning.enums import ReviewPlace

# Confirmed by the project's author. Do not add ambiguous generic abbreviations.
ALIASES={
 'Совещание администрации школы':ReviewPlace.ADMINISTRATIVE_MEETING,
 'ДЖК':ReviewPlace.DIRECTOR_COUNCIL,'ДЖО':ReviewPlace.DIRECTOR_COUNCIL,
 'ӘКО':ReviewPlace.METHOD_COUNCIL,'Әдістемелік отырысы':ReviewPlace.METHOD_COUNCIL,
 'Әдістеме-лік отырысы':ReviewPlace.METHOD_COUNCIL,'ПК':ReviewPlace.PED_COUNCIL,
 'ӘБ отырысы':ReviewPlace.METHOD_ASSOC,
 'ҒӘК':ReviewPlace.SCIENTIFIC_ACADEMY_COUNCIL,'ҒББ':ReviewPlace.SCIENTIFIC_ACADEMY_COUNCIL,
}

def key(value):
    raw=str(getattr(value,'value',value)or'')
    return re.sub(r'[\s.\-()«»]+','',unicodedata.normalize('NFC',raw).casefold())

@lru_cache(maxsize=1)
def labels():
    result=dict(ALIASES)
    for place in ReviewPlace:
        for label in (place.value,place.label_kz,place.label_ru,place.full_kz,place.full_ru,
                      f'{place.full_kz} ({place.label_kz})'):
            old=result.get(label)
            if old is not None and old!=place:raise RuntimeError('Ambiguous review-place label')
            result[label]=place
    return result

@lru_cache(maxsize=1)
def normalized_labels():
    result={}
    for label,place in labels().items():
        normalized=key(label)
        if normalized in result and result[normalized]!=place:raise RuntimeError('Ambiguous review-place alias')
        result[normalized]=place
    return result


def parse_place(value):
    if isinstance(value,ReviewPlace):return value
    return normalized_labels().get(key(value))


def label_for_message(value,language):
    # Exact lookup keeps ordinary UI translations fast and never splits prose.
    if not isinstance(value,str):return None
    place=labels().get(value)
    return place.display_label(language) if place is not None else None


def legacy_places(value):
    raw=str(getattr(value,'value',value)or'').strip()
    if not raw:return set()
    result=set()
    for part in re.split(r'[,;/\n]+',raw):
        if not part.strip():continue
        place=parse_place(part)
        if place is None:return None
        result.add(place.value)
    return result
