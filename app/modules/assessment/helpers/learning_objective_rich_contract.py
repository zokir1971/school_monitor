"""Pure contracts for official objective text, LaTeX and programme scope."""
from __future__ import annotations
import re
from typing import Any, Mapping

MAX_TEXT = 20000
MAX_LATEX = 4000
FORBIDDEN_LATEX = re.compile(r"\\(?:href|url|html\w*|includegraphics|input|include|write|def|gdef|newcommand"
                             r"|renewcommand|require)\b", re.I)


def validate_program_scope(meta: dict[str, Any]) -> None:
    first, last = meta['grade_from'], meta['grade_to']
    track = meta.get('education_track', '').strip().lower()
    has_upper = first <= 11 and last >= 10
    if has_upper:
        if not 10 <= first <= last <= 11:
            raise ValueError('Загрузите 10–11 классы отдельно от остальных классов.')
        if track not in ('emn', 'ogn'):
            raise ValueError('Для 10–11 классов выберите направление ЕМН или ОГН.')
    elif track:
        raise ValueError('Направление допускается только для 10 и 11 классов.')
    if meta.get('instruction_language') not in ('kz', 'ru', 'uz_ug_tg'):
        raise ValueError('Выберите язык обучения: казахский, русский или уйгурский / узбекский / таджикский.')
    meta['education_track'] = track


def normalize_segments(raw: object, *, fallback: str, label: str) -> list[dict[str, str]]:
    if raw is None:
        raw = [{'type': 'text', 'text': fallback}] if fallback else []
    if not isinstance(raw, list) or len(raw) > 200:
        raise ValueError(f'{label}: неверная структура текста и формул.')
    segments: list[dict[str, str]] = []
    total = 0
    for segment in raw:
        if not isinstance(segment, dict) or segment.get('type') not in ('text', 'latex'):
            raise ValueError(f'{label}: разрешены только text и latex.')
        kind, value = segment['type'], segment.get('text')
        if not isinstance(value, str):
            raise ValueError(f'{label}: ожидается текст сегмента.')
        if kind == 'latex':
            value = value.strip()
            if not value or len(value) > MAX_LATEX or FORBIDDEN_LATEX.search(value):
                raise ValueError(f'{label}: пустая, слишком длинная или неподдерживаемая формула.')
            if value.startswith('$') or value.endswith('$'):
                raise ValueError(f'{label}: храните LaTeX без внешних знаков $.')
        if not value:
            continue
        total += len(value)
        if total > MAX_TEXT:
            raise ValueError(f'{label}: максимум {MAX_TEXT} символов.')
        if segments and kind == 'text' and segments[-1]['type'] == 'text':
            segments[-1]['text'] += value
        else:
            segments.append({'type': kind, 'text': value})
    return segments


def segments_text(segments: list[dict[str, str]]) -> str:
    """Readable fallback includes full LaTeX for existing search and AI consumers."""
    return ''.join(s['text'] if s['type'] == 'text' else '$$' + s['text'] + '$$' for s in segments).strip()


def validate_rich_row(row: Mapping[str, Any], *, label: str, require_kz: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for language in ('kz', 'ru'):
        flag = row.get('has_formula_' + language, False)
        reviewed = row.get('formula_reviewed_' + language, False)
        if type(flag) is not bool or type(reviewed) is not bool:
            raise ValueError(f'{label}: отметки формул должны быть булевыми.')
        title = row.get('title_' + language, '')
        if not isinstance(title, str):
            raise ValueError(f'{label}: неверный текст {language.upper()}.')
        segments = normalize_segments(row.get('title_segments_' + language), fallback=title,
                                      label=label+' '+language.upper())
        has_latex = any(s['type'] == 'latex' for s in segments)
        flag = flag or has_latex
        if flag and not has_latex:
            raise ValueError(f'{label} {language.upper()}: вставьте формулу через редактор.')
        if flag and not reviewed:
            raise ValueError(f'{label} {language.upper()}: подтвердите сверку формул с оригиналом.')
        plain = segments_text(segments)
        if require_kz and language == 'kz' and not plain:
            raise ValueError(f'{label}: заполните казахский текст цели.')
        result['title_' + language] = plain
        result['title_segments_' + language] = segments
        result['has_formula_' + language] = flag
        result['formula_reviewed_' + language] = flag and reviewed
    return result
