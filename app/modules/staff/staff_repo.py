# app/modules/staff/staff_repo.py

from __future__ import annotations

from sqlalchemy import update, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.planning.enums import ResponsibleRole  # enum
from app.modules.staff.models_staff_school import SchoolStaffMember, SchoolStaffRole
from app.modules.users.models import User


class SchoolStaffRepo:

    @staticmethod
    async def list_members(db, *, school_id: int, include_inactive: bool = False):
        q = (
            select(SchoolStaffMember)
            .where(SchoolStaffMember.school_id == school_id)
            .options(selectinload(SchoolStaffMember.roles))
            .order_by(SchoolStaffMember.full_name.asc(), SchoolStaffMember.id.asc())
        )
        if not include_inactive:
            q = q.where(SchoolStaffMember.is_active.is_(True))
        return (await db.execute(q)).scalars().all()

    @staticmethod
    async def get_member(db, *, school_id: int, member_id: int) -> SchoolStaffMember | None:
        q = (
            select(SchoolStaffMember)
            .where(
                SchoolStaffMember.school_id == school_id,
                SchoolStaffMember.id == member_id,
                )
            .options(selectinload(SchoolStaffMember.roles))
            )
        return (await db.execute(q)).scalars().first()

    @staticmethod
    async def get_member_by_user_id(
            db: AsyncSession,
            *,
            user_id: int,
    ) -> SchoolStaffMember | None:
        q = (
            select(SchoolStaffMember)
            .join(User, User.staff_member_id == SchoolStaffMember.id)
            .where(User.id == user_id)
            .options(selectinload(SchoolStaffMember.roles))
        )
        return (await db.execute(q)).scalars().first()

    @staticmethod
    async def get_member_by_iin(db, *, school_id: int, iin: str) -> SchoolStaffMember | None:
        q = select(SchoolStaffMember).where(
            SchoolStaffMember.school_id == school_id,
            SchoolStaffMember.iin == iin,
        )
        return (await db.execute(q)).scalars().first()

    @staticmethod
    async def create_member(
            db,
            *,
            school_id: int,
            full_name: str,
            iin: str,
            position_text: str, **fields) -> SchoolStaffMember:

        m = SchoolStaffMember(
            school_id=school_id,
            full_name=full_name.strip(),
            iin=iin.strip(),
            position_text=position_text,
            **fields,
        )
        db.add(m)
        await db.flush()  # получить m.id
        return m

    @staticmethod
    async def set_member_roles(
            db, *, school_id: int, member_id: int, roles: list[tuple[ResponsibleRole, str]]
    ):
        # удаляем старые роли сотрудника в этой школе
        await db.execute(
            delete(SchoolStaffRole).where(
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.staff_member_id == member_id,
            )
        )
        # добавляем новые
        for role, ctx in roles:
            db.add(
                SchoolStaffRole(
                    school_id=school_id,
                    staff_member_id=member_id,
                    role=role,
                    role_context=(ctx or "").strip(),
                    is_active=True,
                )
            )

    @staticmethod
    async def dismiss_member(db, *, school_id: int, member_id: int):
        await db.execute(
            update(SchoolStaffMember)
            .where(
                SchoolStaffMember.school_id == school_id,
                SchoolStaffMember.id == member_id,
            )
            .values(is_active=False)
        )

    @staticmethod
    async def list_staff_roles_map(db, *, school_id: int):
        """
        Возвращает mapping: role(enum) -> list[SchoolStaffMember]
        """
        q = (
            select(SchoolStaffRole)
            .where(SchoolStaffRole.school_id == school_id, SchoolStaffRole.is_active.is_(True))
            .options(selectinload(SchoolStaffRole.staff_member))
        )
        rows = (await db.execute(q)).scalars().all()
        mp: dict[ResponsibleRole, list[SchoolStaffMember]] = {}
        for r in rows:
            mp.setdefault(r.role, []).append(r.staff_member)
        return mp

    @staticmethod
    async def get_by_iin(db: AsyncSession, *, school_id: int, iin: str) -> SchoolStaffMember | None:
        q = select(SchoolStaffMember).where(
            SchoolStaffMember.school_id == school_id,
            SchoolStaffMember.iin == iin,
        )
        return (await db.execute(q)).scalars().first()

    @staticmethod
    def create(db: AsyncSession, *, member: SchoolStaffMember) -> None:
        db.add(member)


class SchoolStaffRoleRepo:
    @staticmethod
    async def list_by_member(
            db: AsyncSession, *, school_id: int, member_id: int
    ) -> list[SchoolStaffRole]:
        q = select(SchoolStaffRole).where(
            SchoolStaffRole.school_id == school_id,
            SchoolStaffRole.staff_member_id == member_id,
            SchoolStaffRole.is_active == True,  # noqa
        )
        res = await db.scalars(q)
        return list(res.all())

    @staticmethod
    async def delete_by_member(db: AsyncSession, *, school_id: int, member_id: int) -> None:
        await db.execute(
            delete(SchoolStaffRole).where(
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.staff_member_id == member_id,
            )
        )

    @staticmethod
    async def add_many(
            db: AsyncSession,
            *,
            school_id: int,
            member_id: int,
            roles: list[dict[str, str]],
    ) -> None:
        for r in roles:
            db.add(
                SchoolStaffRole(
                    school_id=school_id,
                    staff_member_id=member_id,
                    role=ResponsibleRole(r["role"]),
                    role_context=r.get("context") or "",
                    is_active=True,
                )
            )
        await db.flush()

    @staticmethod
    async def list_holders_for_role(
            db: AsyncSession, *, school_id: int, role: ResponsibleRole
    ) -> list[SchoolStaffRole]:
        q = select(SchoolStaffRole).where(
            SchoolStaffRole.school_id == school_id,
            SchoolStaffRole.role == role,
            SchoolStaffRole.is_active == True,  # noqa
        )
        res = await db.scalars(q)
        return list(res.all())
