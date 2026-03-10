# app/utils/calendar_weeks.py
from dataclasses import dataclass
from datetime import date, timedelta

'''
# генерация недель сетки месяца (Пн–Вс)
def month_weeks_grid(year: int, month: int):
    """
    Возвращает список недель месяца по сетке Пн–Вс.
    Каждая неделя: {week: 1..6, start: date, end: date}
    """
    first_day = date(year, month, 1)

    # понедельник недели, в которую попадает 1-е число
    grid_start = first_day - timedelta(days=first_day.weekday())

    weeks = []

    for i in range(6):  # максимум 6 недель
        start = grid_start + timedelta(days=i * 7)
        end = start + timedelta(days=6)

        # если неделя уже полностью после месяца — останавливаемся
        if start.month != month and end.month != month and start > first_day:
            break

        weeks.append(
            {
                "week": i + 1,
                "start": start,
                "end": end,
            }
        )

    return weeks



# вычисления week_of_month
def week_of_month_from_date(d: date) -> int:
    """
    Возвращает номер недели месяца (1..6) по сетке Пн–Вс
    """
    first = d.replace(day=1)
    grid_start = first - timedelta(days=first.weekday())
    return ((d - grid_start).days // 7) + 1
'''


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
