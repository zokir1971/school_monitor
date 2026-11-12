"""AI-only rich-text normalization; saved/manual question contracts are unchanged."""
from __future__ import annotations

import re
from collections.abc import Sequence

_COMMAND = re.compile(r"\\[A-Za-z]+")
_DELIMITED = re.compile(r"\$\$(.+?)\$\$|\\\((.+?)\\\)|\\\[(.+?)\\\]", re.DOTALL)


def normalize_ai_formula_segments(
    segments: Sequence[dict[str, str]],
) -> tuple[dict[str, str], ...]:
    """Extract explicitly delimited formulas; reject unbounded LaTeX in prose."""
    result: list[dict[str, str]] = []
    for segment in segments:
        if segment['type'] != 'text':
            result.append(dict(segment))
            continue
        value = segment['text']
        offset = 0
        for match in _DELIMITED.finditer(value):
            prose = value[offset:match.start()]
            _append_prose(result, prose)
            expression = next(group for group in match.groups() if group is not None).strip()
            if not expression:
                raise ValueError('AI formula must not be empty.')
            result.append({'type': 'latex', 'text': expression})
            offset = match.end()
        _append_prose(result, value[offset:])
    return tuple(result)


def _append_prose(result: list[dict[str, str]], value: str) -> None:
    if not value.strip():
        # Whitespace joining prose and formulas belongs to the neighbouring text.
        if value and result and result[-1]['type'] == 'text':
            result[-1]['text'] += value
        return
    if _COMMAND.search(value) or '$$' in value or any(mark in value for mark in (r'\(', r'\)', r'\[', r'\]')):
        raise ValueError(
            'AI returned LaTeX inside a text segment. '
            'Formulas must be separate segments with type="latex". '
            'AI вернул формулу обычным текстом; требуется отдельный сегмент latex.'
        )
    result.append({'type': 'text', 'text': value})
