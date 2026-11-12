# app/modules/org/repositories/org_lookup_repo.py

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.org.models import (
    District,
    School, Region,
)


class OrgLookupRepo:
    """
    Компактные lookup-запросы организационной структуры.

    Используется там, где не требуется загрузка
    полного ORM-графа Region / District / School.
    """

    # =====================================================
    # SCHOOL NAMES
    # =====================================================

    @staticmethod
    async def get_school_names_by_ids(
        db: AsyncSession,
        *,
        school_ids: Sequence[int],
    ) -> dict[int, str]:
        ids = tuple(
            dict.fromkeys(
                school_ids
            )
        )

        if not ids:
            return {}

        stmt = (
            select(
                School.id.label(
                    "school_id"
                ),
                School.name.label(
                    "school_name"
                ),
            )
            .where(
                School.id.in_(
                    ids
                )
            )
        )

        rows = (
            await db.execute(stmt)
        ).all()

        return {
            int(row.school_id): (
                row.school_name or f"ID {row.school_id}"
            )
            for row in rows
        }

    # =====================================================
    # DISTRICT NAMES
    # =====================================================

    @staticmethod
    async def get_district_names_by_ids(
        db: AsyncSession,
        *,
        district_ids: Sequence[int],
    ) -> dict[int, str]:
        ids = tuple(
            dict.fromkeys(
                district_ids
            )
        )

        if not ids:
            return {}

        stmt = (
            select(
                District.id.label(
                    "district_id"
                ),
                District.name.label(
                    "district_name"
                ),
            )
            .where(
                District.id.in_(
                    ids
                )
            )
        )

        rows = (
            await db.execute(stmt)
        ).all()

        return {
            int(row.district_id): (
                row.district_name
                or f"ID {row.district_id}"
            )
            for row in rows
        }

    # =====================================================
    # REGION NAMES
    # =====================================================

    @staticmethod
    async def get_region_names_by_ids(
            db: AsyncSession,
            *,
            region_ids: Sequence[int],
    ) -> dict[int, str]:
        ids = tuple(
            dict.fromkeys(
                region_ids
            )
        )

        if not ids:
            return {}

        stmt = (
            select(
                Region.id.label(
                    "region_id"
                ),
                Region.name.label(
                    "region_name"
                ),
            )
            .where(
                Region.id.in_(
                    ids
                )
            )
        )

        rows = (
            await db.execute(stmt)
        ).all()

        return {
            int(row.region_id): (
                    row.region_name
                    or f"ID {row.region_id}"
            )
            for row in rows
        }

    # =====================================================
    # ORGANIZATION SCOPE CHECKS
    # =====================================================

    @staticmethod
    async def district_belongs_to_region(
            db: AsyncSession,
            *,
            district_id: int,
            region_id: int,
    ) -> bool:
        """
        Проверяет принадлежность района указанной области.

        Используется для проверки организационного scope
        без загрузки ORM-объекта District.
        """

        stmt = select(
            exists().where(
                District.id == district_id,
                District.region_id == region_id,
            )
        )

        return bool(
            await db.scalar(stmt)
        )

    @staticmethod
    async def school_belongs_to_district(
            db: AsyncSession,
            *,
            school_id: int,
            district_id: int,
    ) -> bool:
        """
        Проверяет принадлежность школы указанному району.

        Используется для проверки организационного scope
        без загрузки ORM-объекта School.
        """

        stmt = select(
            exists().where(
                School.id == school_id,
                School.district_id == district_id,
            )
        )

        return bool(
            await db.scalar(stmt)
        )
