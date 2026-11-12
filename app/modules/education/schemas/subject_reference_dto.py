"""Input and presentation contracts for the global Subject reference."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Any
import re

RU_TRANSLITERATION = {'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
                      'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
                      'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
                      'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu',
                      'я': 'ya'}


def subject_code_from_ru(name: str) -> str:
    name = _text(name, "Название RU", required=True, limit=255)
    value = "".join(RU_TRANSLITERATION.get(char, char) for char in name.lower())
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    if not value:
        raise ValueError("Название RU должно содержать русские или латинские буквы либо цифры.")
    if len(value) > 100:
        raise ValueError("Название RU слишком длинное для кода предмета: сократите его.")
    return value


CODE_PATTERN = re.compile(r'[a-z0-9][a-z0-9_-]{0,99}')


@dataclass(frozen=True, slots=True)
class SubjectReferenceInput:
    code: str
    name_kz: str
    name_ru: str | None
    sort_order: int = 100
    is_active: bool = True
    category_id: int | None = None
    curriculum_role: str = 'general'
    apply_policy: bool = False


@dataclass(frozen=True, slots=True)
class SubjectReferenceRow:
    id: int
    code: str
    name_kz: str
    name_ru: str | None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime
    category_id: int | None = None
    curriculum_role: str | None = None


@dataclass(frozen=True, slots=True)
class SubjectReferencePage:
    rows: list[SubjectReferenceRow]
    query: str
    state: str
    page: int
    pages: int
    total: int
    page_size: int
    category_id: int | None = None


def _text(raw: object, label: str, *, required: bool, limit: int) -> str:
    if not isinstance(raw, str):
        raise ValueError(f'{label}: ожидается текст.')
    value = raw.strip()
    if required and not value:
        raise ValueError(f'Заполните поле «{label}».')
    if len(value) > limit:
        raise ValueError(f'{label}: максимум {limit} символов.')
    return value


def parse_subject_form(raw: Mapping[str, Any], *, editing: bool = False) -> SubjectReferenceInput:
    name_kz = _text(raw.get('name_kz', ''), 'Название KZ', required=True, limit=255)
    name_ru = _text(raw.get('name_ru', ''), 'Название RU', required=not editing, limit=255) or None
    code = (_text(raw.get('code', ''), 'Код', required=True, limit=100)
            if editing else subject_code_from_ru(name_ru))
    order = str(raw.get('sort_order', '100')).strip()
    if not re.fullmatch(r'\d{1,6}', order) or not 0 <= int(order) <= 100000:
        raise ValueError('Порядок отображения: целое число от 0 до 100000.')
    active = raw.get('is_active')
    if active not in (None, '', 'yes'):
        raise ValueError('Некорректное значение активности предмета.')
    category = str(raw.get('category_id', '')).strip()
    if not re.fullmatch(r'[1-9][0-9]{0,9}', category):
        raise ValueError('Выберите категорию предмета.')
    role = str(raw.get('curriculum_role', ''))
    from app.modules.education.helpers.curriculum_policy import POLICIES
    if role not in POLICIES:
        raise ValueError('Выберите правила преподавания.')
    return SubjectReferenceInput(category_id=int(category), curriculum_role=role,
                                 apply_policy=raw.get('apply_policy') == 'yes', code=code, name_kz=name_kz,
                                 name_ru=name_ru,
                                 sort_order=int(order), is_active=active == 'yes')
