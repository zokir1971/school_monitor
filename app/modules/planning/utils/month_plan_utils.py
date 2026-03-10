

ACADEMIC_MONTHS = {9, 10, 11, 12, 1, 2, 3, 4, 5}


def is_academic_month(month: int) -> bool:
    return month in ACADEMIC_MONTHS


def month_to_quarter(month: int) -> int:
    if month in (9, 10, 11):
        return 1
    if month in (12, 1, 2):
        return 2
    if month in (3, 4, 5):
        return 3
    return 4