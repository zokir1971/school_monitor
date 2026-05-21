# app/modules/users/report_schemas.py (Схема Pydantic v2 (from_attributes=True) для JSON/API)


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
