"""Multi-part numeric questions; legacy numeric questions keep their contract."""
import re
from decimal import Decimal, InvalidOperation, localcontext
from app.modules.assessment.services.question_bank_media_service import validate_media_segment

_PATTERN = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


def numeric_value(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Ответ и допуск должны быть конечными числами.")
    text = str(value).strip()
    if len(text) > 128 or not _PATTERN.fullmatch(text):
        raise ValueError("Введите число без единицы измерения (например, -2.5).")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Некорректное число.") from exc
    if not result.is_finite() or abs(result.adjusted()) > 308 or result.as_tuple().exponent < -308:
        raise ValueError("Число вне поддерживаемого диапазона.")
    return result


def part_count(max_score):
    score = numeric_value(max_score)
    if score != score.to_integral_value() or not 1 <= score <= 100:
        raise ValueError("Для числового задания укажите целый максимальный балл от 1 до 100.")
    return int(score)


def validate_number_parts(content, answer_key, grading_settings, *, max_score=None,
                          require_parts=False, allow_images=True):
    if "parts" not in content:
        if require_parts:
            raise ValueError("AI должен вернуть выражения в content.parts.")
        return  # Existing legacy structural validator remains responsible for this version.
    parts = content["parts"]
    if not isinstance(parts, list) or not 1 <= len(parts) <= 100:
        raise ValueError("Необходимо от 1 до 100 числовых пунктов.")
    if "value" in answer_key or "unit" in content or "tolerance" in grading_settings:
        raise ValueError("Нельзя смешивать старый и многопунктный числовой формат.")
    identifiers = []
    for part in parts:
        if not isinstance(part, dict):
            raise ValueError("Пункт должен быть объектом.")
        identifier = part.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or len(identifier) > 64:
            raise ValueError("У каждого пункта должен быть строковый id (до 64 символов).")
        identifiers.append(identifier)
        if "unit" in part and (not isinstance(part["unit"], str) or not part["unit"].strip()):
            raise ValueError("Единица измерения должна быть непустой строкой.")
        segments = part.get("segments")
        if not isinstance(segments, list) or not 1 <= len(segments) <= 1000:
            raise ValueError("Каждый пункт должен содержать выражение в segments.")
        for segment in segments:
            if isinstance(segment, dict) and segment.get("type") == "image" and allow_images:
                validate_media_segment(segment)
                continue
            if (not isinstance(segment, dict) or segment.get("type") not in {"text", "latex"}
                    or not isinstance(segment.get("text"), str) or not segment["text"].strip()):
                raise ValueError("В выражении допустимы text, latex и проверенные изображения.")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("id пунктов должны быть уникальными.")
    values = answer_key.get("values")
    if not isinstance(values, dict) or set(values) != set(identifiers):
        raise ValueError("answer_key.values должен содержать ответ для каждого пункта и только для них.")
    for value in values.values():
        numeric_value(value)
    tolerances = grading_settings.get("tolerances", {})
    if not isinstance(tolerances, dict) or set(tolerances) - set(identifiers):
        raise ValueError("Допуски должны относиться только к существующим пунктам.")
    for tolerance in tolerances.values():
        if numeric_value(tolerance) < 0:
            raise ValueError("Допуск не может быть отрицательным.")
    if max_score is not None and len(parts) != part_count(max_score):
        raise ValueError("Количество числовых пунктов должно равняться максимальному баллу.")


def grade_number_parts(*, content, answer_key, grading_settings, answer_data, max_score):
    validate_number_parts(content, answer_key, grading_settings, max_score=max_score, require_parts=True)
    submitted = answer_data.get("values")
    submitted = submitted if isinstance(submitted, dict) else {}
    tolerances = grading_settings.get("tolerances", {})
    count = 0
    for identifier, expected in answer_key["values"].items():
        try:
            actual = numeric_value(submitted.get(identifier))
        except ValueError:
            continue
        with localcontext() as context:
            context.prec = 800
            if abs(actual - numeric_value(expected)) <= numeric_value(tolerances.get(identifier, 0)):
                count += 1
    return Decimal(count), count == len(content["parts"])
