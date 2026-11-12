
from __future__ import annotations
from typing import cast
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy import Table, select, update
from app.modules.education.models import SubjectCategory, Subject


class SubjectCategoryRepo:
    @staticmethod
    async def list_all(db):
        table = cast(Table, SubjectCategory.__table__)
        result = await db.execute(select(table).order_by(table.c.sort_order, table.c.name_ru, table.c.id))
        return [dict(row) for row in result.mappings()]

    @staticmethod
    async def get(db, category_id: int):
        table = cast(Table, SubjectCategory.__table__)
        id_column = cast(ColumnElement[int], table.c["id"])

        result = await db.execute(
            select(table).where(id_column == category_id)
        )
        row = result.mappings().one_or_none()
        return dict(row) if row is not None else None

    @staticmethod
    async def save(db, values, category_id=None):
        table = cast(Table, SubjectCategory.__table__)
        if category_id is None:
            return await db.scalar(table.insert().values(**values).returning(table.c.id))
        id_column = cast(ColumnElement[int], table.c["id"])

        result = await db.execute(
            update(table)
            .where(id_column == category_id)
            .values(**values)
        )

        if result.rowcount != 1:
            raise ValueError('Категория не найдена.')
        return category_id

    @staticmethod
    async def subjects(db):
        table = cast(Table, Subject.__table__)
        result = await db.execute(select(
            table.c.id, table.c.code, table.c.name_kz, table.c.name_ru, table.c.is_active,
            table.c.category_id, table.c.curriculum_role,
        ).order_by(table.c.sort_order, table.c.name_kz, table.c.id))
        return [dict(row) for row in result.mappings()]
