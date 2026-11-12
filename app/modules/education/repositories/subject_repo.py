# app/modules/education/repositories/subject_repo.py

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.education.models import Subject


class SubjectRepo:
    """
    Репозиторий справочника учебных предметов.
    """

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        *,
        subject_id: int,
    ) -> Subject | None:
        stmt = (
            select(Subject)
            .where(
                Subject.id == subject_id,
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_by_id(
        db: AsyncSession,
        *,
        subject_id: int,
    ) -> Subject | None:
        """
        Получить только активный предмет.
        """

        stmt = (
            select(Subject)
            .where(
                Subject.id == subject_id,
                Subject.is_active.is_(True),
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_code(
        db: AsyncSession,
        *,
        code: str,
    ) -> Subject | None:
        stmt = (
            select(Subject)
            .where(
                Subject.code == code,
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_all(
        db: AsyncSession,
    ) -> list[Subject]:
        """
        Активные предметы для select/options интерфейса.
        """

        stmt = (
            select(Subject)
            .where(
                Subject.is_active.is_(True),
            )
            .order_by(
                Subject.sort_order.asc(),
                Subject.name_kz.asc(),
                Subject.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    @staticmethod
    async def get_active_by_ids(
            db: AsyncSession,
            *,
            subject_ids: Sequence[int],
    ) -> list[Subject]:
        """
        не показывается районному сотруднику предметы,
        по которым Assessment вообще никогда не проводился
        """
        ids = tuple(
            dict.fromkeys(
                subject_ids
            )
        )

        if not ids:
            return []

        stmt = (
            select(
                Subject
            )
            .where(
                Subject.id.in_(
                    ids
                ),
                Subject.is_active.is_(True),
            )
            .order_by(
                Subject.name_kz.asc(),
                Subject.id.asc(),
            )
        )

        result = await db.execute(
            stmt
        )

        return list(
            result.scalars().all()
        )
