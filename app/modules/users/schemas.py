# app/modules/users/schemas.py (Схема Pydantic v2 (from_attributes=True) для JSON/API)


from dataclasses import dataclass


@dataclass
class StaffRegisterDTO:
    iin: str
    username: str
    email: str | None
    phone: str | None
    password: str
    password2: str


@dataclass
class StaffLoginDTO:
    identifier: str
    password: str


'''
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.users.enums import UserRole

# ---------------------------
# Constrained primitive types
# ---------------------------

Username = Annotated[str, Field(min_length=2, max_length=50)]
Password = Annotated[str, Field(min_length=4, max_length=128)]
FullName = Annotated[str, Field(min_length=2, max_length=120)]
IIN = Annotated[str, Field(min_length=12, max_length=12, pattern=r"^\d{12}$")]
Phone = Annotated[str, Field(min_length=5, max_length=20)]  # формат можно ужесточить позже
CodeStr = Annotated[str, Field(min_length=4, max_length=64)]


# ---------------------------
# User outputs (SAFE: no IIN)
# ---------------------------

class UserOut(BaseModel):
    """Безопасный вывод пользователя (НИКОГДА не содержит IIN)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: UserRole
    is_active: bool

    email: EmailStr | None = None
    phone: str | None = None

    otp_enabled: bool
    eds_enabled: bool

    # scope
    region_id: int | None = None
    district_id: int | None = None
    school_id: int | None = None

    created_at: datetime
    last_login_at: datetime | None = None


class MeOut(BaseModel):
    user: UserOut


# ---------------------------
# Auth
# ---------------------------

class LoginIn(BaseModel):
    username: Username
    password: Password


class LoginOut(BaseModel):
    """Для API-логина (если понадобится). Для HTML-cookie может не использоваться."""
    user: UserOut


# ---------------------------
# Admin registration by code (L1/L2/L3 admins only)
# ---------------------------

class RegisterAdminIn(BaseModel):
    """Админы регистрируются по коду. Роль/скоуп определяются кодом."""
    code: CodeStr

    username: Username
    password: Password

    iin: IIN
    full_name: FullName

    email: EmailStr | None = None
    phone: str | None = None


class RegisterAdminOut(BaseModel):
    user: UserOut


class RegistrationCodePreviewOut(BaseModel):
    """
    Что показывает preview по коду (до регистрации):
    роль, scope, квота, срок.
    """
    target_role: UserRole
    region_id: int | None = None
    district_id: int | None = None
    school_id: int | None = None
    quota_left: int
    expires_at: datetime | None = None


# ---------------------------
# Staff registration (no code; created by L1/L2; check by IIN)
# ---------------------------

class StaffRegisterIn(BaseModel):
    """Создание сотрудника мониторинга (департамент/район) без кода."""
    username: Username
    password: Password

    iin: IIN
    full_name: FullName

    email: EmailStr | None = None
    phone: str | None = None


class StaffRegisterOut(BaseModel):
    user: UserOut


# ---------------------------
# Teacher registration (no code; created by L3; check by IIN)
# ---------------------------

class TeacherRegisterIn(BaseModel):
    """Создание учителя админом школы (L3) без кода."""
    username: Username
    password: Password

    iin: IIN
    full_name: FullName

    email: EmailStr | None = None
    phone: str | None = None


class TeacherRegisterOut(BaseModel):
    user: UserOut


# ---------------------------
# Registration codes (optional API outputs)
# ---------------------------

class RegistrationCodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code_lookup_hash: str

    target_role: UserRole

    # single scope
    region_id: int | None = None
    district_id: int | None = None
    school_id: int | None = None

    issued_by_user_id: int
    issued_at: datetime

    quota_total: int
    quota_left: int

    is_active: bool
    expires_at: datetime | None = None

    revoked_at: datetime | None = None
    revoked_by_user_id: int | None = None


class RegistrationCodeIssueResult(BaseModel):
    """Результат выдачи кода (raw_code показываем один раз)."""
    raw_code: str
    code: RegistrationCodeOut


class RegistrationCodeUseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code_id: int
    used_by_user_id: int
    used_at: datetime
'''
