"""Versioned multipart single choice. Historical one-answer tasks stay intact."""
import re
from decimal import Decimal
from .number_score_policy import part_count

POLICY = 'per_part_v1'


def single_choice_count(max_score):
    return part_count(max_score)


def validate_single_choice_parts(content, answer_key, grading_settings, *, max_score=None,
                                 require_parts=False, allow_images=True):
    marked = 'parts' in content or 'single_choice_score_policy' in grading_settings
    if not marked and not require_parts:
        return
    if (grading_settings.get('single_choice_score_policy') != POLICY
            or grading_settings.get('partial_credit') is not True):
        raise ValueError('Для пунктов single_choice нужны single_choice_score_policy=per_part_v1 и partial_credit=true.')
    if 'options' in content or 'value' in answer_key:
        raise ValueError('Нельзя смешивать обычный single_choice и пункты задания.')
    parts, values = content.get('parts'), answer_key.get('values')
    if not isinstance(parts, list) or not 1 <= len(parts) <= 100 or not isinstance(values, dict):
        raise ValueError('Нужны от 1 до 100 пунктов и answer_key.values по идентификаторам пунктов.')
    ids = []
    from app.modules.assessment.services.question_bank_media_service import validate_media_segment
    def segments(items):
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise ValueError('Заполните условие и все варианты каждого пункта.')
        for item in items:
            if isinstance(item, dict) and item.get('type') == 'image' and allow_images:
                validate_media_segment(item)
                continue
            if (not isinstance(item, dict) or set(item) != {'type','text'}
                    or item['type'] not in {'text','latex'} or not isinstance(item['text'], str)
                    or not item['text'].strip() or len(item['text']) > 10000):
                raise ValueError('Допустимы непустые текст, формула и разрешённое изображение.')
    for part in parts:
        if not isinstance(part, dict) or set(part) != {'id','segments','options'}:
            raise ValueError('Пункт должен содержать id, segments и options.')
        identifier = part['id']
        if not isinstance(identifier, str) or not re.fullmatch(r'P[1-9][0-9]{0,5}', identifier) or identifier in ids:
            raise ValueError('Пункты должны иметь уникальные идентификаторы P1, P2, … .')
        ids.append(identifier)
        segments(part['segments'])
        options = part['options']
        if (not isinstance(options, list) or len(options) != 4
                or any(not isinstance(o,dict) or set(o) != {'value','segments'} for o in options)
                or [o['value'] for o in options] != list('ABCD')):
            raise ValueError('У каждого пункта нужны ровно четыре варианта A–D по порядку.')
        for option in options: segments(option['segments'])
        value = values.get(identifier)
        if not isinstance(value,str) or value not in list('ABCD'):
            raise ValueError('Выберите один правильный вариант A–D для каждого пункта.')
    if set(values) != set(ids):
        raise ValueError('Ответы должны соответствовать всем пунктам без лишних ключей.')
    if max_score is not None and len(parts) != single_choice_count(max_score):
        raise ValueError('Число пунктов single_choice должно равняться максимальному баллу.')


def grade_single_choice_parts(*, content, answer_key, grading_settings, answer_data, max_score):
    validate_single_choice_parts(content, answer_key, grading_settings, max_score=max_score, require_parts=True)
    submitted = answer_data.get('values')
    if not isinstance(submitted, dict):
        return Decimal(0), False
    correct = sum(isinstance(submitted.get(identifier),str) and submitted.get(identifier)==value
                  for identifier,value in answer_key['values'].items())
    return Decimal(correct), correct == len(content['parts'])
