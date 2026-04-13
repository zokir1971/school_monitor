# app/modules/org/report_repo.py
# -------------------------------------------------------
# Репозиторий для организационной структуры (Region / District / School)
# Здесь ТОЛЬКО SQL-запросы к БД.
# -------------------------------------------------------

from __future__ import annotations

from sqlalchemy import delete, func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.org.models import Region, District, School


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.strip().split())


'''
class OrgRepo:
    # ---------------------------------------------------
    # Получить список областей (Region) для селектора
    # Используется в API /api/org/regions
    # ---------------------------------------------------
    @staticmethod
    async def list_regions(db: AsyncSession) -> list[Region]:
        res = await db.execute(select(Region).order_by(Region.name))
        return list(res.scalars())

    # ---------------------------------------------------
    # Получить список районов по области (Region -> District)
    # Используется в API /api/org/districts
    # ---------------------------------------------------
    @staticmethod
    async def list_districts_by_region(db: AsyncSession, *, region_id: int) -> list[District]:
        res = await db.execute(select(District).where(District.region_id == region_id).order_by(District.name))
        # scalars() отдаёт итератор District-объектов, list() даёт list[District]
        return list(res.scalars())

    # ---------------------------------------------------
    # Получить список школ по району (District -> School)
    # Используется в API /api/org/schools
    # ---------------------------------------------------
    @staticmethod
    async def list_schools_by_district(db: AsyncSession, *, district_id: int) -> list[School]:
        res = await db.execute(
            select(School)
            .where(School.district_id == district_id)
            .order_by(School.name)
        )
        return list(res.scalars())

    # ---------------------------------------------------
    # проверки принадлежности (регион-район-школа)
    # ---------------------------------------------------
    @staticmethod
    async def district_belongs_to_region(db: AsyncSession, *, district_id: int, region_id: int) -> bool:
        res = await db.execute(
            select(District.id).where(
                District.id == district_id,
                District.region_id == region_id,
            )
        )
        return res.scalar_one_or_none() is not None

    @staticmethod
    async def school_belongs_to_district(db: AsyncSession, *, school_id: int, district_id: int) -> bool:
        res = await db.execute(
            select(School.id).where(
                School.id == school_id,
                School.district_id == district_id,
            )
        )
        return res.scalar_one_or_none() is not None
'''


class OrgRepo:
    @staticmethod
    async def list_regions(db: AsyncSession) -> list[Region]:
        result = await db.scalars(
            select(Region).order_by(Region.name)
        )
        return list(result.all())

    @staticmethod
    async def list_districts(
            db: AsyncSession,
            region_id: int | None = None,
    ) -> list[District]:
        stmt = (
            select(District)
            .options(selectinload(District.region))
            .order_by(District.name)
        )

        if region_id is not None:
            stmt = stmt.where(District.region_id == region_id)

        result = await db.scalars(stmt)
        return list(result.all())

    @staticmethod
    async def list_settlements(
            db: AsyncSession,
            *,
            district_id: int,
    ) -> list[str]:
        result = await db.scalars(
            select(School.settlement)
            .where(
                School.district_id == district_id,
                School.settlement.is_not(None),
                School.settlement != "",
            )
            .distinct()
            .order_by(School.settlement)
        )
        return list(result.all())

    @staticmethod
    async def list_schools(
            db: AsyncSession,
            region_id: int | None = None,
            district_id: int | None = None,
            settlement: str | None = None,
            q: str | None = None,
    ) -> list[School]:
        stmt = (
            select(School)
            .options(
                selectinload(School.district).selectinload(District.region)
            )
            .join(School.district)
            .join(District.region)
            .order_by(School.name)
        )

        if region_id is not None:
            stmt = stmt.where(District.region_id == region_id)

        if district_id is not None:
            stmt = stmt.where(School.district_id == district_id)

        if settlement:
            stmt = stmt.where(School.settlement == settlement)

        if q:
            stmt = stmt.where(func.lower(School.name).contains(q.strip().lower()))

        result = await db.scalars(stmt)
        return list(result.unique().all())

    @staticmethod
    async def get_school(db: AsyncSession, school_id: int) -> School | None:
        return await db.scalar(
            select(School)
            .options(
                selectinload(School.district).selectinload(District.region)
            )
            .where(School.id == school_id)
        )

    @staticmethod
    async def create_school(
            db: AsyncSession,
            *,
            district_id: int,
            name: str,
            address: str | None,
    ) -> School:
        clean_name = normalize_text(name)
        clean_address = normalize_text(address) or None

        district = await db.scalar(
            select(District).where(District.id == district_id)
        )
        if not district:
            raise ValueError("Район не найден")

        exists = await db.scalar(
            select(School).where(
                School.district_id == district_id,
                School.name == clean_name,
            )
        )
        if exists:
            raise ValueError("Такая школа уже существует в этом районе")

        school = School(
            district_id=district_id,
            name=clean_name,
            address=clean_address,
        )
        db.add(school)
        await db.commit()
        await db.refresh(school)
        return school

    @staticmethod
    async def update_school(
            db: AsyncSession,
            *,
            school: School,
            district_id: int,
            name: str,
            address: str | None,
    ) -> School:
        clean_name = normalize_text(name)
        clean_address = normalize_text(address) or None

        district = await db.scalar(
            select(District).where(District.id == district_id)
        )
        if not district:
            raise ValueError("Район не найден")

        exists = await db.scalar(
            select(School).where(
                School.district_id == district_id,
                School.name == clean_name,
                School.id != school.id,
            )
        )
        if exists:
            raise ValueError("Такая школа уже существует в этом районе")

        school.district_id = district_id
        school.name = clean_name
        school.address = clean_address

        await db.commit()
        await db.refresh(school)
        return school

    @staticmethod
    async def delete_school(db: AsyncSession, school: School) -> None:
        await db.delete(school)
        await db.commit()

    @staticmethod
    async def delete_schools_bulk(
            db: AsyncSession,
            *,
            school_ids: list[int],
    ) -> None:
        if not school_ids:
            return

        await db.execute(
            delete(School).where(School.id.in_(school_ids))
        )
        await db.commit()
