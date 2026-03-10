# app/utils/edu_experience.py

from datetime import date


def calc_experience_ym(start: date | None, end: date | None = None) -> tuple[int, int] | None:
    """
    Возвращает стаж в (годах, месяцах).
    """
    if not start:
        return None

    end = end or date.today()

    if end < start:
        return (0, 0)

    years = end.year - start.year
    months = end.month - start.month
    days = end.day - start.day

    if days < 0:
        months -= 1

    if months < 0:
        years -= 1
        months += 12

    if years < 0:
        return (0, 0)

    return years, months


def format_experience(start: date | None, end: date | None = None) -> str:
    """
    Возвращает строку вида: '12 лет 3 мес'
    """
    result = calc_experience_ym(start, end)

    if not result:
        return "—"

    years, months = result

    parts = []
    if years:
        parts.append(f"{years} лет")
    if months:
        parts.append(f"{months} мес")

    return " ".join(parts) if parts else "0 мес"
