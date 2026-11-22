# app/modules/users/repositories/workspace_repo.py

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.education.models import Subject, SchoolClass, SchoolClassSubjectTeacher
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

    @staticmethod
    async def has_active_teaching_scope(
        db: AsyncSession,
        *,
        staff_member_id: int,
    ) -> bool:
        """Same active joins as the teaching-scope list; stop after a match."""
        scope = (
            select(SchoolClassSubjectTeacher.id)
            .select_from(SchoolClassSubjectTeacher)
            .join(SchoolClass, SchoolClass.id == SchoolClassSubjectTeacher.school_class_id)
            .join(Subject, Subject.id == SchoolClassSubjectTeacher.subject_id)
            .where(
                SchoolClassSubjectTeacher.staff_member_id == staff_member_id,
                SchoolClassSubjectTeacher.is_active.is_(True),
                SchoolClass.is_active.is_(True),
                Subject.is_active.is_(True),
            )
        )
        result = await db.execute(select(scope.exists()))
        return bool(result.scalar_one())
