# app/modules/staff/utils/staff_require_member.py

from __future__ import annotations

from typing import cast

from fastapi import HTTPException, status

from app.modules.users.models import User


def require_staff_member_id(
    user: User,
) -> int:
    """
    Возвращает SchoolStaffMember.id,
    связанный с текущим пользователем.

    Используется как security boundary
    для teacher-scope.
    """

    staff_member_id = cast(
        int | None,
        user.staff_member_id,
    )

    if staff_member_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Для пользователя не указана "
                "карточка сотрудника школы."
            ),
        )

    return staff_member_id
