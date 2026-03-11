# app/web/jinja_filters.py
from __future__ import annotations

import re
from typing import Any

# Можно вынести в одно место и импортировать везде
MONTH_NAMES_KZ: dict[int, str] = {
    1: "Қаңтар",
    2: "Ақпан",
    3: "Наурыз",
    4: "Сәуір",
    5: "Мамыр",
    6: "Маусым",
    7: "Шілде",
    8: "Тамыз",
    9: "Қыркүйек",
    10: "Қазан",
    11: "Қараша",
    12: "Желтоқсан",
}


def _enum_val(x: Any) -> Any:
    return getattr(x, "value", x)


def _parse_int_list(s: str) -> list[int]:
    # поддержит "9,1,3" / "9; 1; 3" / "9 1 3"
    return [int(x) for x in re.findall(r"\d+", s or "")]


def format_row11_period(
    row: Any,
    current_month: int | None = None,
    month_names: dict[int, str] | None = None,
) -> str:
    """
    Возвращает красивый текст периода для SchoolPlanRow11 / ExportRow11DTO.
    Работает и со старыми полями, и с новыми.
    """
    if not row:
        return ""

    # Если сервис уже подготовил готовый текст — используем его
    ready_text = getattr(row, "period_text", None)
    if ready_text:
        return str(ready_text)

    mn = month_names or MONTH_NAMES_KZ

    pt = _enum_val(getattr(row, "period_type", None))

    # поддержка и старого, и нового имени поля
    pv_int = getattr(row, "period_type_int", None)
    if pv_int is None:
        pv_int = getattr(row, "period_value_int", None)

    pv_values = getattr(row, "period_type_values", None)
    if pv_values is None:
        pv_values = getattr(row, "period_values", None)

    if pt == "quarter":
        return "Тоқсан сайын"

    if pt == "all_year":
        return "Жыл бойы"

    if pt == "monthly":
        return "Ай сайын"

    if pt == "month" and pv_int:
        try:
            month_num = int(pv_int)
        except (TypeError, ValueError):
            month_num = pv_int
        return f"Ай: {mn.get(month_num, str(month_num))}"

    if pt == "months" and pv_values:
        # если pv_values уже список
        if isinstance(pv_values, list):
            nums = []
            for x in pv_values:
                try:
                    nums.append(int(x))
                except (TypeError, ValueError):
                    pass
        else:
            nums = _parse_int_list(str(pv_values))

        if current_month is not None:
            try:
                cm = int(current_month)
            except (TypeError, ValueError):
                cm = None

            if cm is not None and cm in set(nums):
                return f"Ай: {mn.get(cm, str(cm))}"

        names = [mn.get(n, str(n)) for n in nums]
        return f"Айлар: {', '.join(names)}" if names else str(pv_values)

    return str(getattr(row, "deadlines", "") or "")
