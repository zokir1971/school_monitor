# app/modules/org/report_repo.py
# -------------------------------------------------------
# Репозиторий для организационной структуры (Region / District / School)
# Здесь ТОЛЬКО SQL-запросы к БД.
# -------------------------------------------------------

from __future__ import annotations

from sqlalchemy import delete, func, update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import contains_eager, joinedload, raiseload

from app.modules.org.models import Region, District, School, SchoolGovernanceChange
from app.modules.org.governance import normalize_level
from app.modules.users.models import User, RegistrationCode
from app.modules.users.enums import UserRole
from app.common.time import utcnow


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.strip().split())


class OrgRepo:
    @staticmethod
    async def list_schools_json(
        db: AsyncSession, *, region_id=None, district_id=None, q=None
    ):
        stmt = (
            select(
                School.id,
                School.name,
                School.address,
                School.governance_level,
                School.district_id,
                District.name.label("district_name"),
                District.region_id,
                Region.name.label("region_name"),
            )
            .join(District, School.district_id == District.id)
            .join(Region, District.region_id == Region.id)
        )
        if region_id is not None:
            stmt = stmt.where(District.region_id == region_id)
        if district_id is not None:
            stmt = stmt.where(School.district_id == district_id)
        if q and q.strip():
            stmt = stmt.where(
                func.lower(School.name).contains(q.strip().lower(), autoescape=True)
            )
        result = await db.execute(stmt.order_by(School.name, School.id))
        return [dict(row) for row in result.mappings()]

    @staticmethod
    async def list_regions(db: AsyncSession) -> list[Region]:
        result = await db.scalars(
            select(Region).options(raiseload("*")).order_by(Region.name)
        )
        return list(result.all())

    @staticmethod
    async def list_districts(
        db: AsyncSession,
        region_id: int | None = None,
    ) -> list[District]:
        stmt = select(District).options(raiseload("*")).order_by(District.name)

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
        governance_level: str | None = None,
    ) -> list[School]:
        stmt = (
            select(School)
            .join(School.district)
            .join(District.region)
            .options(
                raiseload("*"),
                contains_eager(School.district).contains_eager(District.region),
            )
            .order_by(School.name)
        )

        if region_id is not None:
            stmt = stmt.where(District.region_id == region_id)

        if district_id is not None:
            stmt = stmt.where(School.district_id == district_id)

        if governance_level:
            stmt = stmt.where(School.governance_level == normalize_level(governance_level))

        if settlement:
            stmt = stmt.where(School.settlement == settlement)

        if q:
            stmt = stmt.where(
                func.lower(School.name).contains(q.strip().lower(), autoescape=True)
            )

        result = await db.scalars(stmt)
        return list(result.unique().all())

    @staticmethod
    async def get_school(db: AsyncSession, school_id: int) -> School | None:
        return await db.scalar(
            select(School)
            .join(School.district)
            .join(District.region)
            .options(
                raiseload("*"),
                contains_eager(School.district).contains_eager(District.region),
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
        region_id: int | None = None,
        governance_level: str = "district",
    ) -> School:
        clean_name = normalize_text(name)
        clean_address = normalize_text(address) or None

        district = await db.scalar(
            select(District)
            .options(raiseload("*"), joinedload(District.region))
            .where(District.id == district_id)
        )
        if not district or (region_id is not None and district.region_id != region_id):
            raise ValueError("Район не найден")

        exists = await db.scalar(
            select(School.id).where(
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
            district=district,
            governance_level=normalize_level(governance_level),
        )
        db.add(school)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise
        return school

    @staticmethod
    async def update_school(
        db: AsyncSession,
        *,
        school: School,
        district_id: int,
        name: str,
        address: str | None,
        region_id: int | None = None,
        governance_level: str | None = None,
        actor_user_id: int | None = None,
    ) -> School:
        clean_name = normalize_text(name)
        clean_address = normalize_text(address) or None

        district = await db.scalar(
            select(District)
            .options(raiseload("*"), joinedload(District.region))
            .where(District.id == district_id)
        )
        if not district or (region_id is not None and district.region_id != region_id):
            raise ValueError("Район не найден")

        exists = await db.scalar(
            select(School.id).where(
                School.district_id == district_id,
                School.name == clean_name,
                School.id != school.id,
            )
        )
        if exists:
            raise ValueError("Такая школа уже существует в этом районе")

        # Serialize changes with code issuance and registration. Reload stale ORM state.
        school = await db.scalar(select(School).options(raiseload("*")).where(
            School.id == school.id).with_for_update().execution_options(populate_existing=True))
        if school is None:
            raise ValueError("Школа не найдена")
        new_level = normalize_level(governance_level if governance_level is not None else school.governance_level)
        if new_level != school.governance_level or district_id != school.district_id:
            actor = await db.scalar(select(User.id).where(
                User.id == actor_user_id, User.role == UserRole.SUPERUSER, User.is_active.is_(True)))
            if actor is None:
                raise ValueError("Изменить подчинение или район может только супер администратор / Бағыныстылықты не ауданды тек супер әкімші өзгерте алады")
            db.add(SchoolGovernanceChange(
                school_id=school.id, actor_user_id=actor,
                old_level=school.governance_level, new_level=new_level,
                old_district_id=school.district_id, new_district_id=district_id))
            # Revoke every unspent school-admin quota, including partly consumed codes.
            C = RegistrationCode.__table__
            await db.execute(update(C).where(C.c.school_id == school.id,
                C.c.target_role == UserRole.SCHOOL_ADMIN,
                C.c.is_active.is_(True), C.c.revoked_at.is_(None)).values(
                    is_active=False, revoked_at=utcnow(), revoked_by_user_id=actor))
        school.governance_level = new_level
        school.district = district
        school.district_id = district_id
        school.name = clean_name
        school.address = clean_address

        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise
        return school

    @staticmethod
    async def delete_school(db: AsyncSession, school: School) -> None:
        try:
            await db.delete(school)
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise

    @staticmethod
    async def delete_schools_bulk(
        db: AsyncSession,
        *,
        school_ids: list[int],
    ) -> None:
        if not school_ids:
            return

        try:
            await db.execute(
                delete(School).where(School.id.in_(tuple(dict.fromkeys(school_ids))))
            )
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise
