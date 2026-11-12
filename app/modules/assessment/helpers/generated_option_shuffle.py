"""Reorder new AI single-choice options in memory, synchronously in both languages."""
from copy import deepcopy
from dataclasses import replace
import random
import re

# Explicit option references, not mathematical variables A/B/C/D.
REFERENCE = re.compile(r'((?:правильн\w*\s+ответ\w*|ответ\w*|вариант\w*|дұрыс\s+жауап|жауап|нұсқа|correct\s+answer|answer|option)\s*(?:[:—–=\-]\s*)?)([A-Z])(?![\w])', re.I)
HEADER = re.compile(r'(?m)(?:^|(?<=\n))\s*(?:(?:P|Задание\s*|Пункт\s*|Тапсырма\s*)?(\d+)\s*[).:]?)\s*')


def remap_explanation(text, maps):
    if not text or not REFERENCE.search(text):
        return text
    def rewrite(value, mapping):
        return REFERENCE.sub(lambda m: m.group(1) + mapping.get(m.group(2).upper(), m.group(2)), value)
    if len(maps) == 1:
        return rewrite(text, maps[0])
    headers = list(HEADER.finditer(text))
    # Never guess which task an unscoped answer reference belongs to.
    if not headers or REFERENCE.search(text[:headers[0].start()]):
        raise ValueError('Unscoped option reference in multipart explanation')
    result = text[:headers[0].start()]
    for index, header in enumerate(headers):
        number = int(header.group(1))
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        block = text[header.start():end]
        if not 1 <= number <= len(maps):
            if REFERENCE.search(block):
                raise ValueError('Unknown task in option explanation')
            result += block
        else:
            result += rewrite(block, maps[number - 1])
    return result


def shuffle_generated_options(response, *, rng=None):
    """Return a copy; source DTOs, existing records, and manual edits are untouched.

    Correct positions are balanced within this response for equal option alphabets.
    Small batches need not contain all four letters. No cross-request DB counter.
    """
    rng = rng or random.SystemRandom()
    metadata = deepcopy(response.metadata)
    translated = metadata.get('bilingual_payloads')
    if translated is None and metadata.get('bilingual_payload') is not None:
        translated = [metadata['bilingual_payload']]
    if translated is not None and len(translated) != len(response.questions):
        raise ValueError('Translation count does not match source question count')
    bags = {}
    warnings = list(response.warnings)
    questions = []
    for qindex, original in enumerate(response.questions):
        if getattr(original.question_type, 'value', original.question_type) not in {'single_choice', 'image_choice'}:
            questions.append(original)
            continue
        content, key = deepcopy(original.content), deepcopy(original.answer_key)
        target = deepcopy(translated[qindex]) if translated is not None else None
        parts = content.get('parts')
        containers = parts if parts is not None else [content]
        target_parts = (target['content'].get('parts') if parts is not None else [target['content']]) if target is not None else None
        if target_parts is not None and len(target_parts) != len(containers):
            raise ValueError('Translated parts do not match source')
        mappings = []
        for index, container in enumerate(containers):
            part_id = container['id'] if parts is not None else None
            options = container['options']
            labels = [option['value'] for option in options]
            if len(set(labels)) != len(labels) or len(labels) < 2:
                raise ValueError('Single-choice options must have unique values')
            correct = key['values'][part_id] if parts is not None else key['value']
            if correct not in labels:
                raise ValueError('Correct option does not exist')
            alphabet = tuple(labels)
            if not bags.get(alphabet):
                bags[alphabet] = labels[:]
                rng.shuffle(bags[alphabet])
            desired = bags[alphabet].pop()
            order = [i for i, option in enumerate(options) if option['value'] != correct]
            rng.shuffle(order)
            order.insert(labels.index(desired), labels.index(correct))
            mapping = {labels[old]: labels[new] for new, old in enumerate(order)}
            container['options'] = [dict(deepcopy(options[old]), value=labels[new]) for new, old in enumerate(order)]
            if parts is not None:
                key['values'][part_id] = mapping[correct]
            else:
                key['value'] = mapping[correct]
            if target is not None:
                other = target_parts[index]
                if parts is not None and other['id'] != part_id:
                    raise ValueError('Translated task IDs do not match')
                target_options = other['options']
                if [option['value'] for option in target_options] != labels:
                    raise ValueError('Translated option values do not match')
                old_correct = target['answer_key']['values'][part_id] if parts is not None else target['answer_key']['value']
                if old_correct != correct:
                    raise ValueError('Translated answer key does not match')
                other['options'] = [dict(deepcopy(target_options[old]), value=labels[new]) for new, old in enumerate(order)]
                if parts is not None:
                    target['answer_key']['values'][part_id] = mapping[correct]
                else:
                    target['answer_key']['value'] = mapping[correct]
            mappings.append(mapping)
        try:
            explanation = remap_explanation(original.explanation, mappings)
            if target is not None:
                target['explanation'] = remap_explanation(target.get('explanation'), mappings)
        except ValueError:
            # Preserve a valid original rather than corrupt an ambiguous explanation.
            questions.append(original)
            warnings.append(f'Задание {qindex + 1}: варианты не перемешаны — пронумеруйте задания в пояснении. / {qindex + 1}-тапсырма: нұсқалар араластырылмады — түсіндірмедегі тапсырмаларды нөмірлеңіз.')
            continue
        question = replace(original, content=content, answer_key=key, explanation=explanation)
        if target is not None:
            from .bilingual_question_contract import source_payload, assert_variant_contract
            source_data = source_payload(question)
            source_data['text_segments'] = list(source_data.get('text_segments') or [])
            assert_variant_contract(source_data, target, question.question_type)
            translated[qindex] = target
        questions.append(question)
    if translated is not None:
        metadata['bilingual_payloads'] = translated
        metadata['bilingual_payload'] = translated[0]
    return replace(response, questions=tuple(questions), warnings=tuple(warnings), metadata=metadata)
