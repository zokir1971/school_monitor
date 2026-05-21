# app/utils/calendar_weeks.py
from dataclasses import dataclass
from datetime import date, timedelta


def calc_year_from_academic(academic_year: str, month: int) -> int:
    # "2025-2026" -> (2025, 2026)
    y1_s, y2_s = (academic_year or "").split("-", 1)
    y1, y2 = int(y1_s), int(y2_s)
    return y1 if 9 <= month <= 12 else y2


@dataclass(frozen=True)
class WeekRange:
    week: int  # 1..6
    start: date  # monday
    end: date  # sunday


def month_weeks_grid(year: int, month: int) -> list[WeekRange]:
    """
    Сетка календаря Пн–Вс для указанного месяца.
    Неделя 1 — та, в которую попадает 1-е число.
    Возвращает 4..6 недель.
    """
    first = date(year, month, 1)
    grid_start = first - timedelta(days=first.weekday())  # Monday=0

    weeks: list[WeekRange] = []
    for i in range(6):
        start = grid_start + timedelta(days=i * 7)
        end = start + timedelta(days=6)

        # если неделя полностью после месяца — стоп
        if start.month != month and end.month != month and start > first:
            break

        weeks.append(WeekRange(week=i + 1, start=start, end=end))

    return weeks
