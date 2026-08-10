# app/core/storage/schemas.py (Результат сохранения и контекст школы)

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SchoolStorageContext:
    region_id: int
    district_id: int
    school_id: int

    academic_year: str

    school_plan_id: int | None = None
    month_item_id: int | None = None


@dataclass(frozen=True, slots=True)
class StoredFile:
    object_key: str
    stored_file_name: str
    original_file_name: str
    content_type: str
    file_size: int
    e_tag: str | None = None
