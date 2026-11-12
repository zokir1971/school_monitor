"""Versioned fill-gaps: one point for each correctly filled gap."""
import re
from decimal import Decimal
from app.modules.assessment.helpers.number_score_policy import part_count

POLICY = "per_gap_v1"
_SOURCE_GAPS = re.compile(r"\[\[([^\[\]\r\n]+)]]")


def validate_fill_source(source):
    if not isinstance(source, str):
        raise ValueError("Введите текст с ответами в [[двойных скобках]].")
    matches = list(_SOURCE_GAPS.finditer(source))
    remainder = _SOURCE_GAPS.sub("", source)
    if ("[[" in remainder or "]]" in remainder or any(not m.group(1).strip()
            or m.start() > 0 and source[m.start() - 1] == "["
            or m.end() < len(source) and source[m.end()] == "]" for m in matches)):
        raise ValueError("Проверьте скобки: каждый пропуск должен иметь непустой ответ вида [[ответ]].")
    if not matches:
        raise ValueError("Добавьте хотя бы один пропуск [[ответ]].")
    return len(matches)


def validate_fill_gaps_score(content, answer_key, grading_settings, *, max_score=None, require_policy=False):
    if "fill_gaps_score_policy" not in grading_settings and not require_policy:
        return
    if grading_settings.get("fill_gaps_score_policy") != POLICY or grading_settings.get("partial_credit") is not True:
        raise ValueError("Новый fill_gaps требует fill_gaps_score_policy=per_gap_v1 и partial_credit=true.")
    for flag in ("case_sensitive", "trim_whitespace"):
        if flag in grading_settings and type(grading_settings[flag]) is not bool:
            raise ValueError(f"{flag} должен быть bool.")
    if content.get("input_mode") not in {"text_input", "word_bank"}:
        raise ValueError("Неизвестный способ заполнения пропусков.")
    segments = content.get("segments")
    if not isinstance(segments, list) or not 1 <= len(segments) <= 1000:
        raise ValueError("Нужен непустой список сегментов текста и пропусков.")
    ids = []
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError("Сегмент должен быть объектом.")
        if segment.get("type") == "gap":
            if set(segment) != {"type", "gap_id"} or not isinstance(segment["gap_id"], str):
                raise ValueError("Сегмент gap содержит только type и gap_id, без правильного ответа.")
            ids.append(segment["gap_id"])
        elif segment.get("type") == "text":
            if set(segment) != {"type", "text"} or not isinstance(segment["text"], str) or not segment["text"]:
                raise ValueError("Текстовый сегмент должен содержать непустую строку.")
            if "[[" in segment["text"] or "]]" in segment["text"]:
                raise ValueError("Пропуск должен быть gap-сегментом, а не скобками в тексте.")
        else:
            raise ValueError("fill_gaps поддерживает сегменты text и gap.")
    if not 1 <= len(ids) <= 100 or ids != [f"G{i+1}" for i in range(len(ids))]:
        raise ValueError("Пропуски должны иметь уникальные последовательные gap_id G1, G2, ... (от 1 до 100).")
    gaps = answer_key.get("gaps")
    if not isinstance(gaps, dict) or set(gaps) != set(ids):
        raise ValueError("Для каждого пропуска нужен отдельный список допустимых ответов.")
    accepted = set()
    for settings in gaps.values():
        values = settings.get("accepted_answers") if isinstance(settings, dict) else None
        if (not isinstance(values, list) or not 1 <= len(values) <= 100
                or any(not isinstance(v, str) or not v.strip() or "[" in v or "]" in v or "\n" in v or "\r" in v for v in values)):
            raise ValueError("Допустимые ответы должны быть непустыми строками без квадратных скобок и переносов строк.")
        if len(set(values)) != len(values):
            raise ValueError("Не повторяйте одинаковые допустимые ответы внутри одного пропуска.")
        accepted.update(values)
    if "word_bank_format" in content:
        from app.modules.assessment.helpers.fill_gaps_rich_bank import validate_bank
        if grading_settings.get("fill_gaps_score_policy") != POLICY:
            raise ValueError("Rich bank requires per_gap_v1 scoring.")
        validate_bank(content, answer_key)
        return _validate_rich_projection(content, answer_key, grading_settings, max_score)
    if content["input_mode"] == "word_bank":
        bank = content.get("word_bank")
        if (not isinstance(bank, list) or not bank or any(not isinstance(v, str) or not v.strip() for v in bank)
                or len(set(bank)) != len(bank) or not accepted.issubset(set(bank))):
            raise ValueError("Словарь должен включать все допустимые ответы без повторов.")
    elif "word_bank" in content:
        raise ValueError("Словарь не используется при самостоятельном вводе ответа.")
    if max_score is not None and len(ids) != part_count(max_score):
        raise ValueError("Количество пропусков должно равняться максимальному баллу: 1 балл за пропуск.")


def _validate_rich_projection(content, answer_key, grading_settings, max_score):
    projected = {**content, "word_bank": [item["value"] for item in content["word_bank"]]}
    projected.pop("word_bank_format")
    validate_fill_gaps_score(projected, answer_key, grading_settings, max_score=max_score, require_policy=True)


def grade_fill_gaps(*, content, answer_key, grading_settings, answer_data, max_score):
    validate_fill_gaps_score(content, answer_key, grading_settings, max_score=max_score, require_policy=True)
    submitted = answer_data.get("gaps")
    submitted = submitted if isinstance(submitted, dict) else {}
    def normalized(value):
        if content.get("word_bank_format") == "rich_v1":
            return value  # IDs are opaque and case-sensitive; variants are reusable.
        if grading_settings.get("trim_whitespace", True):
            value = value.strip()
        return value if grading_settings.get("case_sensitive", False) else value.casefold()
    score = 0
    for identifier, settings in answer_key["gaps"].items():
        value = submitted.get(identifier)
        if isinstance(value, str) and normalized(value) in {normalized(v) for v in settings["accepted_answers"]}:
            score += 1
    return Decimal(score), score == len(answer_key["gaps"])
