# app/modules/assessment/helpers/formula_contract_rules.py
"""Структура FORMULA: обозначения, варианты значений и правильные связи."""
import re


def validate_formula_meanings(content, answer_key, grading_settings):
    fields_present = 'meaning_options' in content or 'variable_meanings' in answer_key
    required = grading_settings.get('variable_meanings_required', False)
    if not isinstance(required, bool):
        raise ValueError('variable_meanings_required must be bool.')
    if not fields_present and not required:
        return  # Ранее сохранённая FORMULA без второго шага.
    variables = content.get('variables')
    if not isinstance(variables, list) or not 1 <= len(variables) <= 30:
        raise ValueError('1–30 формула белгіленуін енгізіңіз.')
    if any(not isinstance(v, str) or not v.strip() or v != v.strip() or len(v) > 80 for v in variables):
        raise ValueError('Формула белгіленулері қате.')
    if len(set(variables)) != len(variables):
        raise ValueError('Формула белгіленулері қайталанбауы керек.')
    options = content.get('meaning_options')
    if not isinstance(options, list) or not 1 <= len(options) <= 50:
        raise ValueError('1–50 шама атауын енгізіңіз.')
    ids, labels = set(), set()
    for option in options:
        if not isinstance(option, dict):
            raise ValueError('Шама нұсқасы қате.')
        key, label = option.get('value'), option.get('label')
        if not isinstance(key, str) or not re.fullmatch(r'M[1-9][0-9]*', key) or key in ids:
            raise ValueError('Шама нұсқасының идентификаторы қате.')
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > 200 or label.strip() in labels:
            raise ValueError('Шама атауы бос немесе қайталанған (ең көбі 200 таңба).')
        ids.add(key); labels.add(label.strip())
    meanings = answer_key.get('variable_meanings')
    if not isinstance(meanings, dict) or set(meanings) != set(variables):
        raise ValueError('Әр белгіленудің дұрыс шамасын көрсетіңіз.')
    if any(not isinstance(value, str) or value not in ids for value in meanings.values()):
        raise ValueError('Белгіленудің жауабы бар шама нұсқасына сәйкес болуы керек.')
    target = content.get('target_variable')
    if target is not None and (not isinstance(target, str) or target not in variables):
        raise ValueError('Өрнектелетін шама белгіленулер тізімінде болуы керек.')
