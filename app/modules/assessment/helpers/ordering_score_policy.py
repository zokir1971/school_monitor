"""Versioned ordering: one point per correct position; legacy is unchanged."""
from collections import Counter
from decimal import Decimal
import json
import random
from app.modules.assessment.helpers.number_score_policy import part_count
from app.modules.assessment.services.question_bank_media_service import validate_media_segment

POLICY = "per_position_v1"


def ordering_count(max_score):
    count = part_count(max_score)
    if count < 2:
        raise ValueError("Для определения порядка требуется от 2 до 100 целых баллов.")
    return count


def validate_ordering_score(content, answer_key, grading_settings, *, max_score=None,
                            require_policy=False, allow_images=True):
    if "ordering_score_policy" not in grading_settings and not require_policy:
        return
    if grading_settings.get("ordering_score_policy") != POLICY or grading_settings.get("partial_credit") is not True:
        raise ValueError("Новый порядок требует ordering_score_policy=per_position_v1 и partial_credit=true.")
    items = content.get("items")
    if not isinstance(items, list) or not 2 <= len(items) <= 100:
        raise ValueError("Необходимо от 2 до 100 элементов.")
    identifiers = []; signatures = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"value", "segments"}:
            raise ValueError("Элемент должен содержать только value и segments.")
        value = item["value"]
        if not isinstance(value, str) or not value.strip() or len(value) > 64:
            raise ValueError("У каждого элемента должен быть строковый value (до 64 символов).")
        identifiers.append(value)
        segments = item["segments"]
        if not isinstance(segments, list) or not 1 <= len(segments) <= 1000:
            raise ValueError("Каждый элемент должен содержать текст или формулу.")
        for segment in segments:
            if isinstance(segment, dict) and segment.get("type") == "image" and allow_images:
                validate_media_segment(segment); continue
            if (not isinstance(segment, dict) or segment.get("type") not in {"text", "latex"}
                    or not isinstance(segment.get("text"), str) or not segment["text"].strip()):
                raise ValueError("Допустимы непустые text/latex сегменты и проверенные изображения.")
        signatures.append(json.dumps(segments, sort_keys=True, ensure_ascii=False))
    if len(set(identifiers)) != len(identifiers) or len(set(signatures)) != len(signatures):
        raise ValueError("Элементы и их идентификаторы не должны повторяться.")
    order = answer_key.get("order")
    if (not isinstance(order, list) or any(not isinstance(value, str) for value in order)
            or len(order) != len(items) or len(set(order)) != len(order) or set(order) != set(identifiers)):
        raise ValueError("Правильный порядок должен содержать каждый элемент ровно один раз.")
    if max_score is not None and len(items) != ordering_count(max_score):
        raise ValueError("Количество элементов должно равняться максимальному баллу.")


def shuffle_new_ordering(content, answer_key):
    """Shuffle new stored items and relabel positions without changing the correct order."""
    items = list(content["items"])
    random.SystemRandom().shuffle(items)
    if [item["value"] for item in items] == answer_key["order"]:
        items = items[1:] + items[:1]
    remap = {item["value"]: f"I{i+1}" for i, item in enumerate(items)}
    return ({**content, "items": [{**item, "value": remap[item["value"]]} for item in items]},
            {**answer_key, "order": [remap[value] for value in answer_key["order"]]})


def grade_ordering_positions(*, content, answer_key, grading_settings, answer_data, max_score):
    validate_ordering_score(content, answer_key, grading_settings, max_score=max_score, require_policy=True)
    expected = answer_key["order"]
    submitted = answer_data.get("order")
    if not isinstance(submitted, list) or len(submitted) > len(expected):
        return Decimal(0), False
    counts = Counter(value for value in submitted if isinstance(value, str))
    score = sum(isinstance(value, str) and counts[value] == 1 and value == expected[index]
                for index, value in enumerate(submitted))
    return Decimal(score), score == len(expected)
