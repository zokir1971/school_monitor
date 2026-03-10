# app/common/phone.py (телефоны, даты, строки и т.п.)


def normalize_kz_phone(phone: str | None) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())

    # 8XXXXXXXXXX -> 7XXXXXXXXXX
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]

    if len(digits) == 11 and digits.startswith("7"):
        return digits

    return ""
