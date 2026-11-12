# app/modules/assessment/schemas/question_bank_expert_schemas.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


# ============================================================
# COMMAND DTOs
# ============================================================


@dataclass(frozen=True, slots=True)
class QuestionBankExpertCreateDTO:
    """
    Данные для создания предметного экспертного назначения.
    """

    school_id: int
    subject_id: int | None

    iin: str
    full_name: str

    phone: str | None = None
    email: str | None = None

    position_text: str | None = None
    education_text: str | None = None
    specialty_text: str | None = None
    qualification_category_text: str | None = None

    ped_experience_years: int | None = None

    specialty_id: int | None = None
    specialty_name: str = "Требуется настройка"


@dataclass(frozen=True, slots=True)
class QuestionBankExpertUpdateDTO:
    """
    Изменяемые сведения эксперта.

    ИИН сохраняется. Специальность можно изменить через specialty_id.
    Исторический предмет не используется для определения полномочий.
    """

    school_id: int

    full_name: str

    phone: str | None = None
    email: str | None = None

    position_text: str | None = None
    education_text: str | None = None
    specialty_text: str | None = None
    qualification_category_text: str | None = None

    ped_experience_years: int | None = None


# ============================================================
# PAGE DTOs
# ============================================================

    specialty_id: int | None = None
    specialty_name: str = "Требуется настройка"


@dataclass(frozen=True, slots=True)
class QuestionBankExpertListItemDTO:
    expert_id: int

    iin: str
    full_name: str

    school_id: int
    school_name: str

    district_id: int
    district_name: str

    region_id: int
    region_name: str

    subject_id: int | None
    subject_name: str

    qualification_category_text: str | None
    ped_experience_years: int | None

    user_id: int | None
    has_account: bool

    is_active: bool

    created_at: datetime

    specialty_id: int | None = None
    specialty_name: str = "Требуется настройка"
    specialty_name_kz: str | None = None


@dataclass(frozen=True, slots=True)
class QuestionBankExpertSchoolDTO:
    school_id: int
    school_name: str

    district_id: int
    district_name: str


@dataclass(frozen=True, slots=True)
class QuestionBankExpertDistrictDTO:
    district_id: int
    district_name: str


@dataclass(frozen=True, slots=True)
class QuestionBankExpertSubjectDTO:
    subject_id: int | None
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class QuestionBankExpertPageDTO:
    """
    Полностью подготовленные данные страницы реестра.
    """

    region_id: int

    experts: list[QuestionBankExpertListItemDTO]
    districts: list[QuestionBankExpertDistrictDTO]
    schools: list[QuestionBankExpertSchoolDTO]
    subjects: list[QuestionBankExpertSubjectDTO]


@dataclass(frozen=True, slots=True)
class QuestionBankExpertFormOptionsDTO:
    """
    Справочные данные для форм создания
    и редактирования эксперта.

    Намеренно не содержит список экспертов.
    """

    schools: list[QuestionBankExpertSchoolDTO]
    subjects: list[QuestionBankExpertSubjectDTO]

    specialties: list[dict] = field(default_factory=list)


# ============================================================
# DETAIL DTO
# ============================================================


@dataclass(frozen=True, slots=True)
class QuestionBankExpertDetailDTO:
    expert_id: int

    iin: str
    full_name: str

    phone: str | None
    email: str | None

    school_id: int
    school_name: str

    district_id: int
    district_name: str

    region_id: int
    region_name: str

    subject_id: int | None
    subject_code: str
    subject_name: str

    position_text: str | None
    education_text: str | None
    specialty_text: str | None
    qualification_category_text: str | None

    ped_experience_years: int | None

    user_id: int | None
    has_account: bool

    is_active: bool

    created_by_user_id: int
    created_at: datetime
    updated_at: datetime

    deactivated_by_user_id: int | None
    deactivated_at: datetime | None
    specialty_id: int | None = None
    specialty_name: str = "Требуется настройка"
    specialty_name_kz: str | None = None
