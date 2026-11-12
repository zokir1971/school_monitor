# app/modules/education/repositories/student_repo.py

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.education.models import SchoolStudent


class SchoolStudentRepo:
    """
    Репозиторий контингента учащихся.

    SchoolStudent не является User.
    """

    @staticmethod
    async def get_by_id(
            db: AsyncSession,
            *,
            student_id: int,
    ) -> SchoolStudent | None:
        stmt = (
            select(SchoolStudent)
            .where(
                SchoolStudent.id == student_id,
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id_for_school(
            db: AsyncSession,
            *,
            student_id: int,
            school_id: int,
    ) -> SchoolStudent | None:
        """
        Получить ученика только внутри указанной школы.
        """

        stmt = (
            select(SchoolStudent)
            .where(
                SchoolStudent.id == student_id,
                SchoolStudent.school_id == school_id,
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_many_by_ids_for_school(
            db: AsyncSession,
            *,
            student_ids: Sequence[int],
            school_id: int,
    ) -> list[SchoolStudent]:
        ids = tuple(dict.fromkeys(student_ids))

        if not ids:
            return []

        stmt = (
            select(SchoolStudent)
            .where(
                SchoolStudent.school_id == school_id,
                SchoolStudent.id.in_(ids),
            )
            .order_by(
                SchoolStudent.last_name.asc(),
                SchoolStudent.first_name.asc(),
                SchoolStudent.middle_name.asc().nullsfirst(),
                SchoolStudent.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    @staticmethod
    async def get_active_by_school(
            db: AsyncSession,
            *,
            school_id: int,
    ) -> list[SchoolStudent]:
        stmt = (
            select(SchoolStudent)
            .where(
                SchoolStudent.school_id == school_id,
                SchoolStudent.is_active.is_(True),
            )
            .order_by(
                SchoolStudent.last_name.asc(),
                SchoolStudent.first_name.asc(),
                SchoolStudent.middle_name.asc().nullsfirst(),
                SchoolStudent.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    @staticmethod
    async def get_by_external_identity(
            db: AsyncSession,
            *,
            school_id: int,
            source_system: str,
            external_id: str,
    ) -> SchoolStudent | None:
        """
        Поиск ученика при синхронизации с внешней системой,
        например НОБД.
        """

        stmt = (
            select(SchoolStudent)
            .where(
                SchoolStudent.school_id == school_id,
                SchoolStudent.source_system == source_system,
                SchoolStudent.external_id == external_id,
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_iin(
            db: AsyncSession,
            *,
            school_id: int,
            iin: str,
    ) -> SchoolStudent | None:
        stmt = (
            select(SchoolStudent)
            .where(
                SchoolStudent.school_id == school_id,
                SchoolStudent.iin == iin,
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_by_school(db: AsyncSession, *, school_id: int) -> list[SchoolStudent]:
        """Include inactive students to avoid duplicates on reimport."""
        result = await db.execute(select(SchoolStudent).where(SchoolStudent.school_id == school_id))
        return list(result.scalars().all())

    @staticmethod
    def add_many(db: AsyncSession, students: Sequence[SchoolStudent]) -> None:
        db.add_all(list(students))

    @staticmethod
    async def flush(db: AsyncSession) -> None:
        await db.flush()
