# app/modules/reports/rules/checking_notebooks.py
from __future__ import annotations

from typing import Any


def calculate_max_score(
    *,
    criteria: list[Any],
    score_scale: list[Any] | None = None,
) -> int:
    """
    Максимально возможный балл для формы проверки тетрадей.

    Приоритет:
    1. собственные scores критерия;
    2. общая score_scale;
    3. 0, если шкала не определена.
    """
    total = 0
    fallback_scale = score_scale or []

    for criterion in criteria:
        criterion_scores = (
            criterion.get("scores")
            if isinstance(criterion, dict)
            else None
        )

        values = criterion_scores if criterion_scores else fallback_scale

        numeric_values: list[int] = []

        if isinstance(values, dict):
            iterable = values.keys()
        else:
            iterable = values or []

        for value in iterable:
            try:
                numeric_values.append(int(value))
            except (TypeError, ValueError):
                continue

        if numeric_values:
            total += max(numeric_values)

    return total


def calculate_percent(
    *,
    total_score: int,
    max_score: int,
) -> int:
    if max_score <= 0:
        return 0

    return round(total_score * 100 / max_score)


def calculate_level(percent: int) -> str:
    if percent >= 90:
        return "Жоғары"
    if percent >= 70:
        return "Жеткілікті"
    if percent >= 50:
        return "Орташа"
    return "Төмен"
