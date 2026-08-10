# app/modules/reports/utils/parsing.py
from __future__ import annotations

from datetime import datetime


def parse_optional_datetime(value: str | None) -> datetime | None:
    """
    Преобразовать ISO datetime-строку в datetime.
    Пустое или некорректное значение возвращает None.
    """
    if not value or not value.strip():
        return None

    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None
