"""Rich word-bank validation. Answers are opaque IDs, never rendered expressions."""
import re

FORMAT = 'rich_v1'


def shuffle_bank(content):
    """Shuffle new display order while keeping answer IDs stable."""
    from secrets import SystemRandom
    bank = list(content['word_bank'])
    if len(bank) > 1:
        before = [item['value'] for item in bank]
        SystemRandom().shuffle(bank)
        if [item['value'] for item in bank] == before:
            bank = bank[1:] + bank[:1]
    return {**content, 'word_bank': bank}


def validate_bank(content, answer_key):
    if content.get('input_mode') != 'word_bank' or content.get('word_bank_format') != FORMAT:
        raise ValueError('Rich bank requires word_bank mode and word_bank_format=rich_v1.')
    bank = content.get('word_bank')
    if not isinstance(bank, list) or not 1 <= len(bank) <= 300:
        raise ValueError('Банк должен содержать от 1 до 300 вариантов.')
    identifiers, expressions = set(), set()
    for item in bank:
        if not isinstance(item, dict) or set(item) != {'value', 'segments'}:
            raise ValueError('Вариант банка содержит value и segments.')
        value, segments = item['value'], item['segments']
        if not isinstance(value, str) or not re.fullmatch(r'W[1-9][0-9]{0,5}', value) or value in identifiers:
            raise ValueError('Варианты должны иметь уникальные ID W1, W2, ... .')
        identifiers.add(value)
        if not isinstance(segments, list) or not 1 <= len(segments) <= 50:
            raise ValueError('Заполните текст или формулу каждого варианта.')
        for segment in segments:
            if (not isinstance(segment, dict) or set(segment) != {'type', 'text'}
                    or segment['type'] not in {'text', 'latex'}
                    or not isinstance(segment['text'], str) or not segment['text'].strip()
                    or len(segment['text']) > 4000):
                raise ValueError('Варианты банка поддерживают непустые сегменты text и latex.')
        signature = tuple((s['type'], s['text'].strip()) for s in segments)
        if signature in expressions:
            raise ValueError('Не дублируйте одинаковые варианты: один вариант можно использовать в нескольких пропусках.')
        expressions.add(signature)
    gaps = answer_key.get('gaps')
    if not isinstance(gaps, dict) or not gaps:
        raise ValueError('Укажите правильные варианты для каждого пропуска.')
    for gap in gaps.values():
        values = gap.get('accepted_answers') if isinstance(gap, dict) else None
        if (not isinstance(values, list) or not values
                or any(not isinstance(v, str) or v not in identifiers for v in values)
                or len(set(values)) != len(values)):
            raise ValueError('Правильные ответы должны ссылаться на существующие уникальные ID банка.')
    return [item['value'] for item in bank]
