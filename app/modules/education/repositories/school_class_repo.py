# app/modules/education/repositories/school_class_repo.py

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.education.models import SchoolClass


class SchoolClassRepo:
    """
    Репозиторий учебных классов школы.
    """

    @staticmethod
    async def get_by_id(
            db: AsyncSession,
            *,
            class_id: int,
    ) -> SchoolClass | None:
        stmt = (
            select(SchoolClass)
            .where(
                SchoolClass.id == class_id,
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id_for_school(
            db: AsyncSession,
            *,
            class_id: int,
            school_id: int,
    ) -> SchoolClass | None:
        """
        Получить класс с обязательной проверкой школы.
        """

        stmt = (
            select(SchoolClass)
            .where(
                SchoolClass.id == class_id,
                SchoolClass.school_id == school_id,
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_many_by_ids_for_school(
            db: AsyncSession,
            *,
            class_ids: Sequence[int],
            school_id: int,
    ) -> list[SchoolClass]:
        """
        Получить несколько классов одной школы.

        Используется при создании Assessment,
        который может охватывать несколько классов.
        """

        ids = tuple(dict.fromkeys(class_ids))

        if not ids:
            return []

        stmt = (
            select(SchoolClass)
            .where(
                SchoolClass.school_id == school_id,
                SchoolClass.id.in_(ids),
            )
            .order_by(
                SchoolClass.academic_year_start.asc(),
                SchoolClass.grade_level.asc(),
                SchoolClass.letter.asc(),
                SchoolClass.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    @staticmethod
    async def get_active_by_school_and_year(
            db: AsyncSession,
            *,
            school_id: int,
            academic_year_start: int,
    ) -> list[SchoolClass]:
        """
        Активные классы школы за конкретный учебный год.
        """

        stmt = (
            select(SchoolClass)
            .where(
                SchoolClass.school_id == school_id,
                SchoolClass.academic_year_start
                == academic_year_start,
                SchoolClass.is_active.is_(True),
            )
            .order_by(
                SchoolClass.grade_level.asc(),
                SchoolClass.letter.asc(),
                SchoolClass.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    @staticmethod
    async def get_active_by_school_grade_year(
            db: AsyncSession,
            *,
            school_id: int,
            academic_year_start: int,
            grade_level: int,
    ) -> list[SchoolClass]:
        """
        Активная параллель.

        Например:
            9А
            9Б
            9В
        """

        stmt = (
            select(SchoolClass)
            .where(
                SchoolClass.school_id == school_id,
                SchoolClass.academic_year_start
                == academic_year_start,
                SchoolClass.grade_level == grade_level,
                SchoolClass.is_active.is_(True),
            )
            .order_by(
                SchoolClass.letter.asc(),
                SchoolClass.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    @staticmethod
    async def get_active_grade_levels(
            db: AsyncSession,
            *,
            school_id: int,
            academic_year_start: int,
    ) -> tuple[int, ...]:
        stmt = (
            select(
                SchoolClass.grade_level
            )
            .where(
                SchoolClass.school_id == school_id,
                SchoolClass.academic_year_start
                == academic_year_start,
                SchoolClass.is_active.is_(True),
            )
            .distinct()
            .order_by(
                SchoolClass.grade_level.asc()
            )
        )

        result = await db.execute(stmt)

        return tuple(
            int(value)
            for value in result.scalars().all()
        )

    @staticmethod
    async def get_all_by_school(db: AsyncSession, *, school_id: int) -> list[SchoolClass]:
        """All years and inactive classes, for import identity/history checks."""
        result = await db.execute(select(SchoolClass).where(SchoolClass.school_id == school_id))
        return list(result.scalars().all())

    @staticmethod
    def add_many(db: AsyncSession, classes: Sequence[SchoolClass]) -> None:
        db.add_all(list(classes))

    @staticmethod
    async def flush(db: AsyncSession) -> None:
        await db.flush()
