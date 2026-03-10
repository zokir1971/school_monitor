# app/modules/users/deps.py

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db  # ✅ единая dependency из db/session.py
from app.modules.users.models import User
from app.modules.users.enums import UserRole
from app.modules.users.repo import UserRepo


# --- Auth: cookie session ---
def _get_session_user_id(request: Request) -> int | None:
    raw = request.cookies.get("user_id")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def get_current_user(
        request: Request,
        db: AsyncSession = Depends(get_db),
) -> User:
    user_id = _get_session_user_id(request)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = await UserRepo.get_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    return user


def require_roles(*roles: UserRole):
    async def _dep(user: User = Depends(get_current_user)) -> User:
        # SUPERUSER всегда проходит
        if user.role == UserRole.SUPERUSER:
            return user

        if roles and user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        return user

    return _dep


# --- Scope helpers ---
def require_region_scope(user: User = Depends(get_current_user)) -> User:
    """Операции уровня области."""
    if user.role == UserRole.SUPERUSER:
        return user
    if user.role != UserRole.REGION_ADMIN or user.region_id is None:
        raise HTTPException(status_code=403, detail="Region scope required")
    return user


def require_district_scope(user: User = Depends(get_current_user)) -> User:
    """Операции уровня района."""
    if user.role == UserRole.SUPERUSER:
        return user
    if user.role != UserRole.DISTRICT_ADMIN or user.district_id is None:
        raise HTTPException(status_code=403, detail="District scope required")
    return user


def require_school_admin_scope(user: User = Depends(get_current_user)) -> User:
    """Администраторские операции уровня школы (планы, управление пользователями школы и т.п.)."""
    if user.role == UserRole.SUPERUSER:
        return user
    if user.role != UserRole.SCHOOL_ADMIN or user.school_id is None:
        raise HTTPException(status_code=403, detail="School admin scope required")
    return user


def require_teacher_scope(user: User = Depends(get_current_user)) -> User:
    """Операции, доступные учителю."""
    if user.role == UserRole.SUPERUSER:
        return user
    if user.role != UserRole.SCHOOL_STAFF or user.school_id is None:
        raise HTTPException(status_code=403, detail="Teacher scope required")
    return user


def require_school_member_scope(user: User = Depends(get_current_user)) -> User:
    """Любой пользователь школы: SCHOOL_ADMIN или TEACHER."""
    if user.role == UserRole.SUPERUSER:
        return user
    if user.role not in (UserRole.SCHOOL_ADMIN, UserRole.SCHOOL_STAFF) or user.school_id is None:
        raise HTTPException(status_code=403, detail="School member scope required")
    return user
