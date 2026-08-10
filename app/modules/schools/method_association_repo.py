# app/modules/schools/method_association_repo.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reviews.models_task_review import (
    SchoolMethodAssociation,
)


class SchoolMethodAssociationRepository:

    @staticmethod
    async def get_all_by_school(
        db: AsyncSession,
        *,
        school_id: int,
    ) -> list[SchoolMethodAssociation]:
        """
        Возвращает все методические объединения школы,
        включая неактивные.
        """

        stmt = (
            select(SchoolMethodAssociation)
            .where(
                SchoolMethodAssociation.school_id == school_id,
            )
            .order_by(
                SchoolMethodAssociation.name.asc(),
                SchoolMethodAssociation.id.asc(),
            )
        )

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
