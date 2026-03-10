# app/modules/users/validators.py (Валидация правильной привязки ролей)

import re
import secrets

from app.core.security import registration_code_lookup_hash
from app.modules.users.enums import UserRole
from app.common.phone import normalize_kz_phone


def validate_user_scope(
        role: UserRole,
        region_id: int | None,
        district_id: int | None,
        school_id: int | None,
) -> None:
    # SUPERUSER: без привязки к оргструктуре
    if role == UserRole.SUPERUSER:
        if region_id is not None or district_id is not None or school_id is not None:
            raise ValueError(
                "SUPERUSER не должен иметь region_id/district_id/school_id (все должны быть NULL)."
            )
        return

    # REGION_ADMIN: только region_id
    if role == UserRole.REGION_ADMIN:
        if region_id is None or district_id is not None or school_id is not None:
            raise ValueError(
                "REGION_ADMIN должен иметь region_id, а district_id/school_id должны быть NULL."
            )
        return

    # DISTRICT_ADMIN: только district_id
    if role == UserRole.DISTRICT_ADMIN:
        if district_id is None or region_id is not None or school_id is not None:
            raise ValueError(
                "DISTRICT_ADMIN должен иметь district_id, а region_id/school_id должны быть NULL."
            )
        return

    # SCHOOL_ADMIN: только school_id
    if role == UserRole.SCHOOL_ADMIN:
        if school_id is None or region_id is not None or district_id is not None:
            raise ValueError(
                "SCHOOL_ADMIN должен иметь school_id, а region_id/district_id должны быть NULL."
            )
        return

    # TEACHER: только school_id
    if role == UserRole.TEACHER:
        if school_id is None or region_id is not None or district_id is not None:
            raise ValueError(
                "TEACHER должен иметь school_id, а region_id/district_id должны быть NULL."
            )
        return

    raise ValueError("Неизвестная роль пользователя.")


IIN_RE = re.compile(r"^\d{12}$")


def validate_iin(iin: str) -> str:
    iin = iin.strip()
    if not IIN_RE.fullmatch(iin):
        raise ValueError("ИИН должен состоять из 12 цифр")
    return iin


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def validate_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not EMAIL_RE.fullmatch(email):
        raise ValueError("Некорректный email")
    return email


KZ_PHONE_RE = re.compile(r"^7\d{10}$")


def validate_kz_phone(phone: str) -> str:
    phone = normalize_kz_phone(phone)

    if not KZ_PHONE_RE.fullmatch(phone):
        raise ValueError("Телефон должен быть в формате 7XXXXXXXXXX")

    return phone


def _make_human_code(prefix: str = "L1", group_len: int = 4) -> str:
    # пример: L1-8F3K
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # без 0/O/1/I
    tail = "".join(secrets.choice(alphabet) for _ in range(group_len))
    return f"{prefix}-{tail}"


def _lookup_hash(code: str) -> str:
    # хэш от нормализованной формы (без дефисов/пробелов, верхний регистр)
    return registration_code_lookup_hash(code)
