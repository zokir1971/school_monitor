"""Versioned, one-to-one matching. Unmarked legacy questions stay unchanged."""
from collections import Counter
from decimal import Decimal
import json
import random
from app.modules.assessment.helpers.number_score_policy import part_count
from app.modules.assessment.services.question_bank_media_service import validate_media_segment

POLICY = "per_pair_v1"


def matching_count(max_score):
    count = part_count(max_score)
    if count < 2:
        raise ValueError("Сопоставление требует от 2 до 100 целых баллов: одна пара — один балл.")
    return count


def validate_matching_score(content, answer_key, grading_settings, *, max_score=None,
                            require_policy=False, allow_images=True):
    policy = grading_settings.get("matching_score_policy")
    if "matching_score_policy" not in grading_settings and not require_policy:
        return
    if policy != POLICY or grading_settings.get("partial_credit") is not True:
        raise ValueError("Новые задания сопоставления требуют matching_score_policy=per_pair_v1 и partial_credit=true.")
    identifiers = {}
    for side in ("left", "right"):
        items = content.get(side)
        if not isinstance(items, list) or not 2 <= len(items) <= 100:
            raise ValueError("В каждом списке должно быть от 2 до 100 элементов.")
        ids = []; signatures = []
        for item in items:
            if not isinstance(item, dict) or set(item) != {"value", "segments"}:
                raise ValueError("Элемент списка должен содержать только value и segments.")
            value = item["value"]
            if not isinstance(value, str) or not value.strip() or len(value) > 64:
                raise ValueError("У каждого элемента должен быть уникальный строковый value (до 64 символов).")
            ids.append(value)
            segments = item["segments"]
            if not isinstance(segments, list) or not 1 <= len(segments) <= 1000:
                raise ValueError("У каждого элемента должен быть непустой текст или формула.")
            for segment in segments:
                if isinstance(segment, dict) and segment.get("type") == "image" and allow_images:
                    validate_media_segment(segment); continue
                if (not isinstance(segment, dict) or segment.get("type") not in {"text", "latex"}
                        or not isinstance(segment.get("text"), str) or not segment["text"].strip()):
                    raise ValueError("Допустимы непустые text/latex сегменты и проверенные изображения.")
            signatures.append(json.dumps(segments, sort_keys=True, ensure_ascii=False))
        if len(set(ids)) != len(ids):
            raise ValueError("Идентификаторы элементов одного списка не должны повторяться.")
        if len(set(signatures)) != len(signatures):
            raise ValueError("Содержимое элементов одного списка не должно повторяться.")
        identifiers[side] = set(ids)
    if len(content["left"]) != len(content["right"]):
        raise ValueError("Число левых и правых элементов должно совпадать.")
    pairs = answer_key.get("pairs")
    if not isinstance(pairs, list) or len(pairs) != len(content["left"]):
        raise ValueError("Для каждого левого элемента нужна одна правильная пара.")
    left = []; right = []
    for pair in pairs:
        if (not isinstance(pair, dict) or set(pair) != {"left", "right"}
                or not isinstance(pair["left"], str) or not isinstance(pair["right"], str)):
            raise ValueError("Каждая пара должна содержать строковые left и right.")
        left.append(pair["left"]); right.append(pair["right"])
    if (set(left) != identifiers["left"] or len(set(left)) != len(left)
            or set(right) != identifiers["right"] or len(set(right)) != len(right)):
        raise ValueError("Сопоставление должно быть взаимно однозначным: каждый элемент используется один раз.")
    if max_score is not None and len(pairs) != matching_count(max_score):
        raise ValueError("Количество пар должно равняться максимальному баллу.")


def shuffle_new_matching(content, answer_key):
    """Prepare only new items for storage. Preserve meaning, avoid aligned lists/ID hints."""
    right = list(content["right"])
    random.SystemRandom().shuffle(right)
    expected = {pair["left"]: pair["right"] for pair in answer_key["pairs"]}
    if all(expected[item["value"]] == right[i]["value"] for i, item in enumerate(content["left"])):
        right = right[1:] + right[:1]
    # Label the displayed right positions, not the author-entered correct-pair rows.
    remap = {item["value"]: f"R{i+1}" for i, item in enumerate(right)}
    new_content = {**content, "right": [{**item, "value": remap[item["value"]]} for item in right]}
    new_key = {**answer_key, "pairs": [{"left": pair["left"], "right": remap[pair["right"]]} for pair in answer_key["pairs"]]}
    return new_content, new_key


def grade_matching_pairs(*, content, answer_key, grading_settings, answer_data, max_score):
    validate_matching_score(content, answer_key, grading_settings, max_score=max_score, require_policy=True)
    expected = {pair["left"]: pair["right"] for pair in answer_key["pairs"]}
    submitted = answer_data.get("pairs")
    if not isinstance(submitted, list):
        return Decimal(0), False
    # An ambiguous/doubly chosen left or right earns no point for the affected pair.
    pairs = [(pair["left"], pair["right"]) for pair in submitted
             if isinstance(pair, dict) and isinstance(pair.get("left"), str)
             and pair["left"] in expected and isinstance(pair.get("right"), str)]
    left_counts = Counter(left for left, _ in pairs)
    right_counts = Counter(right for _, right in pairs)
    count = sum(left_counts[left] == 1 and right_counts[right] == 1 and expected[left] == right
                for left, right in pairs)
    return Decimal(count), count == len(expected)
