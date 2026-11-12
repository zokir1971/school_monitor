# app/modules/users/repositories/workspace_repo.py

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.staff.models_staff_school import (
    SchoolStaffMember,
)


class UserWorkspaceRepo:
    """
    Repository для определения доступных
    рабочих интерфейсов пользователя.

    Не определяет бизнес-правила workspace.
    Только отвечает на вопросы о наличии
    соответствующих активных данных.
    """

    # =========================================================
    # STAFF
    # =========================================================

    @staticmethod
    async def has_active_staff_member(
        db: AsyncSession,
        *,
        staff_member_id: int,
    ) -> bool:
        """
        Проверяет существование активной записи
        SchoolStaffMember.
        """

        stmt = (
            select(SchoolStaffMember.id)
            .where(
                SchoolStaffMember.id == staff_member_id,
                SchoolStaffMember.is_active.is_(True),
            )
            .limit(1)
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none() is not None
