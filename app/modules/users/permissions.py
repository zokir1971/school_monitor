# app/modules/users/permissions.py
from fastapi import HTTPException
from app.modules.users.enums import UserRole


def assert_can_edit_school(user, *, school_id: int) -> None:
    if user.role == UserRole.SUPERUSER:
        return
    if user.role == UserRole.SCHOOL_ADMIN and user.school_id == school_id:
        return
    raise HTTPException(status_code=403, detail="Нет доступа к плану другой школы")
