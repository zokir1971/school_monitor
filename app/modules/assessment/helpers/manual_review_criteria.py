"""Общие правила критериев ручной проверки: только целые положительные баллы."""
from decimal import Decimal, InvalidOperation
import re

LIMIT = 99999999


def _whole_score(raw, *, field):
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str, Decimal)):
        raise ValueError(f'{field}: укажите положительный целый балл.')
    text = str(raw).strip()
    if len(text) > 128:
        raise ValueError(f'{field}: балл слишком большой.')
    try:
        score = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f'{field}: укажите положительный целый балл.') from exc
    if (not score.is_finite() or not 1 <= score <= LIMIT
            or score != score.to_integral_value()):
        raise ValueError(f'{field}: допустимы только целые баллы от 1 до {LIMIT}, без округления.')
    return int(score)


def validate_manual_criteria(criteria, *, max_score=None):
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= 50:
        raise ValueError('1–50 бағалау критерийін енгізіңіз.')
    maximum = None if max_score is None else _whole_score(max_score, field='Максимальный балл')
    if maximum is not None and len(criteria) > maximum:
        raise ValueError('Количество критериев не может превышать максимальный балл: минимум 1 балл за критерий.')
    seen, normalized = set(), []
    total = 0
    for index, criterion in enumerate(criteria, 1):
        if not isinstance(criterion, dict):
            raise ValueError(f'Критерий {index}: деректер қате.')
        key = criterion.get('id')
        if not isinstance(key, str) or not re.fullmatch(r'C[1-9][0-9]*', key) or key in seen:
            raise ValueError(f'Критерий {index}: бірегей C1, C2… идентификаторы қажет.')
        seen.add(key)
        texts = {}
        for field, limit in [('title', 200), ('description', 2000)]:
            value = criterion.get(field)
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
                raise ValueError(f'{key}: {field} толтырыңыз (ең көбі {limit} таңба).')
            texts[field] = value.strip()
        score = _whole_score(criterion.get('max_score'), field=key)
        total += score
        normalized.append({'id': key, **texts, 'max_score': score})
    if maximum is not None and total != maximum:
        raise ValueError('Критерийлердің балл қосындысы тапсырманың максималды баллына тең болуы керек.')
    return normalized
