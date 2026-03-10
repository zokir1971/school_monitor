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
    Возвращает красивый текст периода для SchoolPlanRow11.
    Работает и для годового шаблона, и для месячного (через source_row11).

    Ожидаемые поля у row:
      - period_type
      - period_value_int
      - period_values
      - deadlines (fallback)

    Красивый текст периода для SchoolPlanRow11.
    Если передан current_month (месячный план), то для period_type="months"
    можно показывать только выбранный месяц.
    """
    if not row:
        return ""

    mn = month_names or MONTH_NAMES_KZ

    pt = _enum_val(getattr(row, "period_type", None))
    pv_int = getattr(row, "period_value_int", None)
    pv_text = getattr(row, "period_values", None)

    if pt == "quarter":
        return "Тоқсан сайын"

    if pt == "all_year":
        return "Жыл бойы"

    if pt == "monthly":
        return "Ай сайын"

    if pt == "month" and pv_int:
        return f"Ай: {mn.get(int(pv_int), str(pv_int))}"

    # ✅ ключевое изменение
    if pt == "months" and pv_text:
        if current_month is not None:
            try:
                cm = int(current_month)
            except (TypeError, ValueError):
                cm = None

            if cm is not None:
                nums = set(_parse_int_list(str(pv_text)))
                if cm in nums:
                    return f"Ай: {mn.get(cm, str(cm))}"

        # fallback: как раньше — показать список
        nums = _parse_int_list(str(pv_text))
        names = [mn.get(n, str(n)) for n in nums]
        return f"Айлар: {', '.join(names)}" if names else str(pv_text)

    return str(getattr(row, "deadlines", "") or "")
