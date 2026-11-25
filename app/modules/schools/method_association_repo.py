# app/modules/schools/method_association_repo.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload
from app.modules.org.models import School

from app.modules.reviews.models_task_review import (
    SchoolMethodAssociation,
)


class SchoolMethodAssociationRepository:

    @staticmethod
    async def lock_school(db: AsyncSession, *, school_id: int) -> bool:
        return await db.scalar(select(School.id).where(School.id == school_id).with_for_update()) is not None

    @staticmethod
    async def get_all_by_school(
        db: AsyncSession,
        *,
        school_id: int,
        refresh: bool = False,
    ) -> list[SchoolMethodAssociation]:
        """
        Возвращает все методические объединения школы,
        включая неактивные.
        """

        stmt = (
            select(SchoolMethodAssociation).options(raiseload("*"))
            .where(
                SchoolMethodAssociation.school_id == school_id,
            )
            .order_by(
                SchoolMethodAssociation.name.asc(),
                SchoolMethodAssociation.id.asc(),
            )
        )

        if refresh:
            stmt = stmt.execution_options(populate_existing=True)
        result = await db.scalars(stmt)
        return list(result.all())

    @staticmethod
    async def get_by_code(
        db: AsyncSession,
        *,
        school_id: int,
        code: str,
    ) -> SchoolMethodAssociation | None:
        """
        Возвращает МО конкретной школы по коду.
        """

        stmt = (
            select(SchoolMethodAssociation)
            .where(
                SchoolMethodAssociation.school_id == school_id,
                SchoolMethodAssociation.code == code,
            )
        )

        return await db.scalar(stmt)

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        school_id: int,
        code: str,
        name: str,
        is_active: bool = True,
    ) -> SchoolMethodAssociation:
        """
        Создаёт методическое объединение школы.
        """

        entity = SchoolMethodAssociation(
            school_id=school_id,
            code=code,
            name=name,
            is_active=is_active,
        )

        db.add(entity)
        await db.flush()

        return entity
