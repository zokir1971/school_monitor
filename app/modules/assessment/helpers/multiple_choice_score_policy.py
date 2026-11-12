"""Authoring rule only. Student grading and historical contracts are unchanged."""
from decimal import Decimal, InvalidOperation


def multiple_choice_answer_count(max_score, option_count: int) -> int:
    if isinstance(max_score, bool) or not isinstance(max_score, (int, float, str, Decimal)):
        raise ValueError('Для нескольких правильных ответов максимальный балл должен быть целым числом.')
    try:
        score = Decimal(str(max_score))
    except InvalidOperation as exc:
        raise ValueError('Некорректный максимальный балл.') from exc
    if not score.is_finite() or score != score.to_integral_value():
        raise ValueError('Для нескольких правильных ответов максимальный балл должен быть целым числом.')
    if score < 2:
        raise ValueError('Для нескольких правильных ответов укажите минимум 2 балла. Для одного ответа выберите «Один правильный ответ».')
    if score >= option_count:
        raise ValueError(f'При {option_count} вариантах максимальный балл должен быть меньше {option_count}: хотя бы один вариант должен быть неверным.')
    return int(score)


def validate_multiple_choice_score(*, content, answer_key, max_score) -> None:
    if not isinstance(content, dict) or not isinstance(answer_key, dict):
        raise ValueError('Варианты и ключ ответов должны быть объектами.')
    options = content.get('options')
    if not isinstance(options, list) or any(not isinstance(o, dict) for o in options):
        raise ValueError('Необходимо указать варианты ответа.')
    option_values = [o.get('value') for o in options]
    if any(not isinstance(v,str) or not v.strip() for v in option_values) or len(set(option_values)) != len(option_values):
        raise ValueError('Идентификаторы вариантов должны быть непустыми и уникальными.')
    required = multiple_choice_answer_count(max_score, len(options))
    values = answer_key.get('values')
    if not isinstance(values, list) or any(not isinstance(v,str) for v in values):
        raise ValueError('Правильные ответы должны быть списком идентификаторов вариантов.')
    if len(set(values)) != len(values) or not set(values).issubset(option_values):
        raise ValueError('Правильные ответы должны быть уникальными и присутствовать среди вариантов.')
    if len(values) != required:
        raise ValueError(f'При максимальном балле {required} необходимо ровно {required} правильных ответа. Сейчас указано: {len(values)}.')
