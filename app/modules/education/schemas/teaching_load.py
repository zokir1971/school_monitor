# app/modules/education/schemas/teaching_load.py

from __future__ import annotations

from dataclasses import dataclass


# =========================================================
# LOOKUP DTO
# =========================================================

@dataclass(slots=True, frozen=True)
class TeachingLoadClassDTO:
    """
    Класс, доступный для назначения учебной нагрузки.
    """

    id: int
    name: str


@dataclass(slots=True, frozen=True)
class TeachingLoadSubjectDTO:
    """
    Предмет, доступный для назначения учебной нагрузки.
    """

    id: int
    name: str


@dataclass(slots=True, frozen=True)
class TeachingLoadTeacherDTO:
    """
    Учитель, доступный для назначения учебной нагрузки.
    """

    staff_member_id: int
    full_name: str


# =========================================================
# ASSIGNMENT DTO
# =========================================================

@dataclass(slots=True, frozen=True)
class TeachingLoadAssignmentDTO:
    """
    Одна активная строка учебной нагрузки.
    """

    id: int

    school_class_id: int
    class_name: str

    subject_id: int
    subject_name: str

    staff_member_id: int | None
    teacher_name: str

    is_primary: bool


# =========================================================
# PAGE DTO
# =========================================================

@dataclass(slots=True, frozen=True)
class TeachingLoadPageDTO:
    """
    Данные страницы управления учебной нагрузкой.
    """

    academic_year_start: int
    academic_year_label: str

    assignments: list[TeachingLoadAssignmentDTO]

    classes: list[TeachingLoadClassDTO]
    subjects: list[TeachingLoadSubjectDTO]
    teachers: list[TeachingLoadTeacherDTO]


# =========================================================
# COMMAND DTO
# =========================================================

@dataclass(slots=True, frozen=True)
class TeachingLoadCreateDTO:
    """
    Команда создания назначения.

    school_id намеренно отсутствует:
    школа определяется сервером по SCHOOL_ADMIN.
    """

    school_class_id: int
    subject_id: int
    staff_member_id: int
    is_primary: bool = True
