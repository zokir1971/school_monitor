"""Persisted plan text, independent of schedule, assignments and workflow enums.

Legacy columns retain the source text. JSON holds independently editable language
versions and source fingerprints. No translation or authored data is cached.
"""
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import fields, is_dataclass, replace

from sqlalchemy import JSON, event, inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column
from app.core.i18n import normalize_language
from app.core.ui_locale_context import ui_locale

ROW4_FIELDS = ('control_object', 'risk_text', 'decision_text')
ROW11_FIELDS = ('topic','goal','control_object','control_type','methods','deadlines',
                'responsibles','review_place','management_decision','second_control')


def language(user=None):
    saved = user.get('ui_language') if isinstance(user, Mapping) else getattr(user,'ui_language',None)
    return normalize_language(saved) or normalize_language(ui_locale.get()) or 'ru'


class LocalizedPlanText:
    text_i18n: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), 'postgresql'),
        nullable=False, default=dict, server_default='{}')
    __text_fields__ = ()


def loaded(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name,default)
    state = getattr(obj,'__dict__',None)
    if state is not None:
        return state.get(name,default)
    return getattr(obj,name,default)


def content_text(obj, field, lang=None, default=''):
    """Read a language version without lazy IO or mutating a tracked ORM row."""
    if obj is None:
        return default
    lang = normalize_language(lang) or language()
    raw = loaded(obj,field)
    data = loaded(obj,'text_i18n')
    # Non-plan DTOs and ordinary application values retain their established API.
    if data is None:
        return raw if raw is not None else default
    base_language = data.get('_base_language','kk')
    baseline = data.get('_base',{})
    # An unadapted Core UPDATE must never display a stale translation.
    if field in baseline and raw != baseline[field]:
        return (raw or default) if lang == base_language else default
    values = data.get(lang,{})
    if field in values:
        return values[field] or default
    # Preexisting rows are Kazakh; new rows record their source language on flush.
    return (raw or default) if lang == base_language else default


def seed_payload(values, *, lang='kk'):
    return {'_base_language':lang,'_base':deepcopy(values),lang:deepcopy(values)}


def write_text(obj, field, value, lang=None):
    """Explicit writers also record clears and values equal to the legacy column."""
    lang = normalize_language(lang) or language()
    data = deepcopy(obj.text_i18n or seed_payload(
        {key:getattr(obj,key,None)for key in obj.__text_fields__}))
    base_lang = data.get('_base_language','kk')
    data.setdefault(lang,{})[field] = value
    if lang == base_lang:
        setattr(obj,field,value)
        data.setdefault('_base',{})[field] = value
    obj.text_i18n = data
    obj.__dict__.setdefault('_i18n_explicit_fields',set()).add(field)


@event.listens_for(Session,'before_flush')
def _record_language_writes(session, flush_context, instances):
    if session.info.get('planning_i18n_seed'):
        return
    lang = language()
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj,LocalizedPlanText):
            continue
        explicit = obj.__dict__.pop("_i18n_explicit_fields",set())
        names = obj.__text_fields__
        state = inspect(obj)
        if obj in session.new:
            if not obj.text_i18n:
                obj.text_i18n = seed_payload({key:getattr(obj,key,None) for key in names},lang=lang)
            continue
        changed = {key:state.attrs[key].history for key in names
                   if key not in explicit and state.attrs[key].history.has_changes()}
        if not changed:
            continue
        data = deepcopy(obj.text_i18n or {})
        base_lang = data.setdefault('_base_language','kk')
        baseline = data.setdefault('_base',{})
        for key,hist in changed.items():
            new = getattr(obj,key)
            old = hist.deleted[0] if hist.deleted else baseline.get(key)
            data.setdefault(base_lang,{}).setdefault(key,old)
            data.setdefault(lang,{})[key] = new
            if lang != base_lang:
                # Preserve the legacy source column; only the selected language is saved.
                setattr(obj,key,old)
                baseline[key] = old
            else:
                baseline[key] = new
        obj.text_i18n = data


class PlanTextView:
    """Small read-only facade: identity/relationships are delegated, text is localized."""
    __slots__ = ('_row','_lang')
    def __init__(self,row,lang):
        object.__setattr__(self,'_row',row)
        object.__setattr__(self,'_lang',lang)
    def __getattr__(self,key):
        if key in self._row.__text_fields__:
            if key == 'review_place':
                from app.modules.planning.template_samples import sample_text
                return sample_text(self._row,key,self._lang)
            value = content_text(self._row,key,self._lang)
            if key == 'short_title' and not value and 'full_title' in self._row.__text_fields__:
                return content_text(self._row,'full_title',self._lang)
            return value
        if key == 'title' and 'title_override' in self._row.__text_fields__:
            if loaded(self._row,'title_override'):
                return content_text(self._row,'title_override',self._lang)
            return content_text(self._row.direction,'short_title',self._lang)
        return display_view(getattr(self._row,key),self._lang)
    def __setattr__(self,key,value):
        raise TypeError('A localized plan view is read-only')


def display_view(value, lang=None):
    lang = normalize_language(lang) or language()
    if isinstance(value,PlanTextView):
        return PlanTextView(value._row,lang)
    if isinstance(value,LocalizedPlanText):
        return PlanTextView(value,lang)
    if isinstance(value,dict):
        return {key:display_view(item,lang) for key,item in value.items()}
    if isinstance(value,list):
        return [display_view(item,lang) for item in value]
    if isinstance(value,tuple):
        return tuple(display_view(item,lang) for item in value)
    if is_dataclass(value) and not isinstance(value,type):
        return replace(value,**{f.name:display_view(getattr(value,f.name),lang)
                               for f in fields(value) if f.init})
    return value


def content_revision(obj,lang=None):
    import hashlib,json
    lang=normalize_language(lang)or language()
    values={key:content_text(obj,key,lang)for key in obj.__text_fields__}
    return hashlib.sha256(json.dumps([obj.id,lang,values],ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()
