# app/web/helpers/request.py

from __future__ import annotations


def parse_optional_int(value: str | None) -> int | None:
    """
    Преобразует строковое значение query-параметра
    в int.

    Возвращает None для пустой строки,
    отсутствующего значения и некорректного числа.
    """

    if value is None:
        return None

    value = value.strip()

    if not value:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_optional_bool(value: str | None) -> bool | None:
    """
    Преобразует query-параметр
    в bool.
    """

    if value is None:
        return None

    value = value.strip().lower()

    if value == "true":
        return True

    if value == "false":
        return False

    return None
