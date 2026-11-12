"""Versioned TRUE_FALSE contracts. Legacy value answers remain supported."""
from decimal import Decimal, InvalidOperation
from app.modules.assessment.services.question_bank_media_service import validate_media_segment


def assertion_count(max_score):
    if isinstance(max_score, bool):
        raise ValueError("Максимальный балл должен быть целым числом от 1 до 100.")
    try:
        score = Decimal(str(max_score))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Максимальный балл должен быть целым числом от 1 до 100.") from exc
    if not score.is_finite() or score != score.to_integral_value() or not 1 <= score <= 100:
        raise ValueError("Максимальный балл должен быть целым числом от 1 до 100.")
    return int(score)


def validate_true_false(content, answer_key, *, max_score=None, require_statements=False, allow_images=True):
    if "statements" not in content:
        if require_statements:
            raise ValueError("AI должен вернуть список утверждений content.statements.")
        if type(answer_key.get("value")) is not bool or "values" in answer_key:
            raise ValueError("Для старого формата требуется answer_key.value типа bool.")
        return
    statements = content["statements"]
    if not isinstance(statements, list) or not 1 <= len(statements) <= 100:
        raise ValueError("Необходимо от 1 до 100 утверждений.")
    ids = []
    for statement in statements:
        if not isinstance(statement, dict):
            raise ValueError("Утверждение должно быть объектом.")
        identifier = statement.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or len(identifier) > 64:
            raise ValueError("У каждого утверждения должен быть непустой строковый id (до 64 символов).")
        ids.append(identifier)
        segments = statement.get("segments")
        if not isinstance(segments, list) or not segments or len(segments) > 1000:
            raise ValueError("Утверждение должно содержать текст или формулу в segments.")
        for segment in segments:
            if isinstance(segment, dict) and segment.get("type") == "image" and allow_images:
                validate_media_segment(segment)
                continue
            if (not isinstance(segment, dict) or segment.get("type") not in {"text", "latex"}
                    or not isinstance(segment.get("text"), str) or not segment["text"].strip()):
                raise ValueError("В утверждениях допустимы text, latex и проверенные изображения.")
    if len(set(ids)) != len(ids):
        raise ValueError("id утверждений должны быть уникальными.")
    values = answer_key.get("values")
    if ("value" in answer_key or not isinstance(values, dict) or set(values) != set(ids)
            or any(type(value) is not bool for value in values.values())):
        raise ValueError("answer_key.values должен содержать bool для каждого id утверждения и только для них.")
    if max_score is not None and len(statements) != assertion_count(max_score):
        raise ValueError("Количество утверждений должно равняться максимальному баллу (1 балл за утверждение).")


def grade_true_false(*, content, answer_key, answer_data, max_score):
    """Return (Decimal score, fully_correct). Missing/invalid student values earn zero."""
    validate_true_false(content, answer_key, max_score=max_score)
    maximum = Decimal(str(max_score))
    if "statements" not in content:
        value = answer_data.get("value")
        correct = type(value) is bool and value is answer_key["value"]
        return (maximum if correct else Decimal(0)), correct
    submitted = answer_data.get("values")
    submitted = submitted if isinstance(submitted, dict) else {}
    correct_count = sum(type(submitted.get(key)) is bool and submitted[key] is expected
                        for key, expected in answer_key["values"].items())
    return Decimal(correct_count), correct_count == len(content["statements"])
