# app/modules/users/enums.py

from __future__ import annotations

import enum


# ============================================================
# GLOBAL USER ROLES
# ============================================================


class UserRole(str, enum.Enum):
    """
    Глобальная роль пользователя в системе.

    UserRole определяет основные полномочия пользователя
    и хранится в users.role.

    Дополнительные рабочие интерфейсы пользователя
    не должны изменять UserRole.
    """

    SUPERUSER = "superuser"

    REGION_ADMIN = "region_admin"
    REGION_STAFF = "region_staff"

    DISTRICT_ADMIN = "district_admin"
    DISTRICT_STAFF = "district_staff"

    SCHOOL_ADMIN = "school_admin"
    SCHOOL_STAFF = "school_staff"

    TEACHER = "teacher"


# ============================================================
# USER WORKSPACES
# ============================================================


class UserWorkspace(str, enum.Enum):
    """
    Активный рабочий интерфейс пользователя.

    Workspace не является глобальной ролью безопасности
    и не изменяет users.role.

    Один пользователь может иметь несколько доступных
    рабочих интерфейсов одновременно.

    Например:

        SCHOOL_ADMIN
            + STAFF
            + TEACHER
            + QUESTION_BANK_EXPERT

    UserRole остаётся SCHOOL_ADMIN, а UserWorkspace
    определяет только текущий интерфейс пользователя.
    """

    # Основной интерфейс глобальной роли пользователя.
    PRIMARY = "primary"

    # Интерфейс сотрудника организации.
    STAFF = "staff"

    # Интерфейс учителя.
    TEACHER = "teacher"

    # Интерфейс предметного эксперта Question Bank.
    QUESTION_BANK_EXPERT = "question_bank_expert"
