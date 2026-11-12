"""Versioned multipart formula authoring. Formula evaluation still requires review."""
import re
from app.modules.assessment.helpers.number_score_policy import numeric_value
from app.modules.assessment.helpers.formula_contract_rules import validate_formula_meanings

POLICY = 'per_part_v1'


def shuffle_formula_options(content):
    """Hide correct symbol-to-meaning order in newly created multipart tasks."""
    from secrets import SystemRandom
    parts = []
    for part in content['parts']:
        options = list(part['meaning_options'])
        before = [option['value'] for option in options]
        SystemRandom().shuffle(options)
        if len(options) > 1 and [option['value'] for option in options] == before:
            options = options[1:] + options[:1]
        parts.append({**part, 'meaning_options': options})
    return {**content, 'parts': parts}


def formula_count(max_score):
    score = numeric_value(max_score)
    if score != score.to_integral_value() or not 1 <= score <= 100:
        raise ValueError('Для формул укажите целый максимальный балл от 1 до 100: один балл за пункт.')
    return int(score)


def validate_formula_parts(content, answer_key, grading_settings, *, max_score=None, require_parts=False):
    if 'parts' not in content and 'formula_score_policy' not in grading_settings and not require_parts:
        return  # Historical single-expression formula; the old validator owns it.
    if (grading_settings.get('formula_score_policy') != POLICY
            or grading_settings.get('partial_credit') is not True
            or grading_settings.get('variable_meanings_required') is not True
            or grading_settings.get('equivalence_mode') != 'exact'):
        raise ValueError('Новый formula требует per_part_v1, partial_credit=true, variable_meanings_required=true и equivalence_mode=exact.')
    if 'trim_whitespace' in grading_settings and type(grading_settings['trim_whitespace']) is not bool:
        raise ValueError('trim_whitespace должен быть bool.')
    if any(name in content for name in ('variables', 'meaning_options', 'target_variable')) or any(name in answer_key for name in ('expression', 'latex', 'variable_meanings')):
        raise ValueError('Нельзя смешивать старый и многопунктный формат формул.')
    parts, keys = content.get('parts'), answer_key.get('parts')
    if not isinstance(parts, list) or not 1 <= len(parts) <= 100 or not isinstance(keys, dict):
        raise ValueError('Нужно от 1 до 100 пунктов формул и ответы в answer_key.parts.')
    ids = []
    for part in parts:
        if (not isinstance(part, dict) or not {'id', 'segments', 'variables', 'meaning_options'}.issubset(part)
                or set(part) - {'id', 'segments', 'variables', 'meaning_options', 'target_variable'}):
            raise ValueError('Пункт формулы содержит id, segments, variables, meaning_options и необязательный target_variable.')
        identifier = part['id']
        if not isinstance(identifier, str) or not re.fullmatch(r'F[1-9][0-9]{0,5}', identifier) or identifier in ids:
            raise ValueError('У пунктов должны быть уникальные ID F1, F2, ... .')
        ids.append(identifier)
        segments = part['segments']
        if not isinstance(segments, list) or not 1 <= len(segments) <= 100:
            raise ValueError('У каждого пункта должно быть условие в segments.')
        for segment in segments:
            if (not isinstance(segment, dict) or set(segment) != {'type', 'text'}
                    or segment['type'] not in {'text', 'latex'} or not isinstance(segment['text'], str)
                    or not segment['text'].strip() or len(segment['text']) > 10000):
                raise ValueError('Условие пункта поддерживает непустые сегменты text и latex.')
        key = keys.get(identifier)
        if not isinstance(key, dict) or set(key) != {'expression', 'variable_meanings'}:
            raise ValueError('Для каждого пункта нужны expression и variable_meanings.')
        if not isinstance(key['expression'], str) or not key['expression'].strip() or len(key['expression']) > 10000:
            raise ValueError('Заполните эталонную формулу каждого пункта.')
        validate_formula_meanings(part, key, grading_settings)
    if set(keys) != set(ids):
        raise ValueError('Ключи answer_key.parts должны точно совпадать с ID пунктов.')
    if max_score is not None and len(parts) != formula_count(max_score):
        raise ValueError('Количество пунктов с формулами должно равняться максимальному баллу.')
