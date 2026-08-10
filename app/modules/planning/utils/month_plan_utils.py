# app/modules/planning/utils/month_plan_utils.py

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.modules.planning.enums import ReviewPlace
from app.modules.planning.constants import (
    ACADEMIC_QUARTERS,
    MONTH_TO_ACADEMIC_QUARTER,
)


def review_place_label(
        value: ReviewPlace | str | None,
) -> str:
    """
    Вернуть казахскую подпись места рассмотрения.
    """

    if value is None:
        return "—"

    if isinstance(value, ReviewPlace):
        return value.label_kz

    try:
        return ReviewPlace(value).label_kz
    except ValueError:
        return str(value)


def review_place_labels(
        values: Iterable[ReviewPlace | str],
) -> list[str]:
    """
    Преобразовать значения ReviewPlace в уникальные подписи.
    """

    labels: list[str] = []

    for value in values:
        label = review_place_label(value)

        if label != "—" and label not in labels:
            labels.append(label)

    return labels


def month_item_review_place_labels(
        review_places: Iterable[Any] | None,
) -> list[str]:
    """
    Получить подписи из ORM-объектов
    SchoolMonthPlanItemReviewPlace.
    """

    if not review_places:
        return []

    return review_place_labels(
        getattr(row, "review_place", None)
        for row in review_places
        if getattr(row, "review_place", None) is not None
    )


def quarter_of_month(month: int) -> int | None:
    """
    Вернуть номер учебной четверти для месяца.

    Август и июнь не входят в учебные четверти.
    """

    return MONTH_TO_ACADEMIC_QUARTER.get(month)


def quarter_months(month: int) -> list[int]:
    """
    Вернуть месяцы учебной четверти,
    в которую входит указанный месяц.
    """

    quarter = quarter_of_month(month)

    if quarter is None:
        return []

    return list(ACADEMIC_QUARTERS[quarter])


def previous_months_in_quarter(month: int) -> list[int]:
    """
    Вернуть предыдущие месяцы текущей учебной четверти.
    """

    months = quarter_months(month)

    if month not in months:
        return []

    return months[:months.index(month)]


def format_short_person_name(
        full_name: str | None,
) -> str:
    """
    Преобразовать полное ФИО в формат:

        ТУРСУНБАЕВА ТОХИРА БАХТИЯРОВНА
        -> ТУРСУНБАЕВА Т.Б.
    """

    if not full_name:
        return "—"

    parts = full_name.split()

    if not parts:
        return "—"

    surname = parts[0]

    initials = "".join(
        f"{part[0]}."
        for part in parts[1:3]
        if part
    )

    if not initials:
        return surname

    return f"{surname} {initials}"
