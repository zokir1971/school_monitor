# app/modules/users/deps.py

from __future__ import annotations

from typing import cast

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db  # ✅ единая dependency из db/session.py
from app.modules.assessment.repositories.question_bank_expert_repo import QuestionBankExpertRepo
from app.modules.users.models import User
from app.modules.users.enums import UserRole, UserWorkspace
from app.modules.users.repo import UserRepo
from app.modules.users.schemas import UserWorkspaceContextDTO
from app.modules.users.services.workspace_service import UserWorkspaceService


# --- Auth: cookie session ---
def _get_session_user_id(request: Request) -> int | None:
    from app.core.access_session import session_user_id
    return session_user_id(request)


async def get_current_user(
        request: Request,
        db: AsyncSession = Depends(get_db),
) -> User:
    user_id = _get_session_user_id(request)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = await UserRepo.get_by_id(db, user_id)
    from app.core.access_session import session_matches
    if not session_matches(request, user):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    from app.core.i18n import resolve_language
    request.state.ui_language = resolve_language(request, user)
    from app.core.ui_locale_context import ui_locale
    ui_locale.set(request.state.ui_language)
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
    """Операции обычного учителя-предметника."""
    if user.role == UserRole.SUPERUSER:
        return user
    if user.role != UserRole.TEACHER or user.school_id is None or user.staff_member_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher scope required",
        )

    return user


def require_school_member_scope(
        user: User = Depends(get_current_user),
) -> User:
    """
    Любой пользователь школьного уровня.
    """

    if user.role == UserRole.SUPERUSER:
        return user

    if (
            user.role not in (
            UserRole.SCHOOL_ADMIN,
            UserRole.SCHOOL_STAFF,
            UserRole.TEACHER,
            )
            or user.school_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="School member scope required",
        )

    return user


# ============================================================
# QUESTION BANK EXPERT
# ============================================================


async def require_question_bank_expert(
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
) -> User:
    """
    Требует активное назначение предметного эксперта
    Question Bank.

    Глобальная UserRole здесь намеренно не проверяется.

    Экспертность является дополнительным полномочием
    пользователя и не изменяет users.role.
    """

    user_id = cast(
        int,
        user.id,
    )

    has_expert_scope = (
        await QuestionBankExpertRepo
        .has_active_expert_scope(
            db,
            user_id=user_id,
        )
    )

    if not has_expert_scope:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Белсенді пәндік сарапшы "
                "тағайындауы табылмады."
            ),
        )

    return user


async def resolve_workspace_context(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
) -> UserWorkspaceContextDTO:
    """
    Определяет workspace-контекст текущего пользователя
    для одного HTTP request.

    Результат сохраняется в request.state, чтобы web-layer
    мог использовать его без повторных запросов к БД.
    """

    from app.modules.users.workspace_choice import requested_workspace as read_workspace
    requested_workspace=read_workspace(request,user)

    workspace_context = (
        await UserWorkspaceService.get_context(
            db,
            user=user,
            requested_workspace=requested_workspace,
        )
    )

    request.state.workspace_context = (
        workspace_context
    )

    return workspace_context


# ============================================================
# WORKSPACE ACCESS
# ============================================================


async def require_teacher_workspace(
        workspace_context: UserWorkspaceContextDTO = Depends(
            resolve_workspace_context
        ),
        user: User = Depends(get_current_user),
) -> User:
    """
    Разрешает доступ к интерфейсу учителя.

    Учитель может получить этот workspace двумя путями:

    1. TEACHER является его глобальной UserRole —
       тогда учительский интерфейс представлен PRIMARY;

    2. TEACHER является дополнительным workspace,
       полученным через teaching scope.
    """

    if user.role == UserRole.TEACHER:
        return user

    has_teacher_workspace = any(
        item.code == UserWorkspace.TEACHER
        for item in workspace_context.items
    )

    if not has_teacher_workspace:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher workspace required",
        )

    return user


async def require_staff_workspace(
        workspace_context: UserWorkspaceContextDTO = Depends(
            resolve_workspace_context
        ),
        user: User = Depends(get_current_user),
) -> User:
    """
    Разрешает доступ к интерфейсу сотрудника школы.

    SCHOOL_STAFF использует свой PRIMARY.
    Для остальных пользователей требуется
    дополнительный STAFF workspace.
    """

    if user.role == UserRole.SCHOOL_STAFF:
        return user

    has_staff_workspace = any(
        item.code == UserWorkspace.STAFF
        for item in workspace_context.items
    )

    if not has_staff_workspace:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff workspace required",
        )

    return user
