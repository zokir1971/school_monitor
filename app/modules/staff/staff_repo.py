# app/modules/staff/staff_repo.py

from __future__ import annotations

from sqlalchemy import delete, select, update, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, raiseload
from types import SimpleNamespace

from app.modules.planning.enums import ResponsibleRole
from app.modules.staff.models_staff_school import (
    SchoolStaffMember,
    SchoolStaffRole,
)
from app.modules.users.models import User


class SchoolStaffRepo:

    # ---------------------------
    # 🔹 Список сотрудников школы
    # ---------------------------
    @staticmethod
    async def list_members(
        db: AsyncSession,
        *,
        school_id: int,
        include_inactive: bool = False,
    ):
        """
        Возвращает список сотрудников школы.

        Особенности:
        - подгружает роли (selectinload)
        - можно включить/исключить неактивных сотрудников
        """
        stmt = (
            select(SchoolStaffMember)
            .where(SchoolStaffMember.school_id == school_id)
            .options(raiseload('*'), selectinload(SchoolStaffMember.roles.and_(SchoolStaffRole.school_id == school_id)))
            .order_by(SchoolStaffMember.full_name.asc(), SchoolStaffMember.id.asc())
        )

        if not include_inactive:
            stmt = stmt.where(SchoolStaffMember.is_active.is_(True))

        result = await db.execute(stmt)
        return result.scalars().all()

    # ---------------------------
    # 🔹 Получить сотрудника по id
    # ---------------------------

    @staticmethod
    async def get_member(
            db: AsyncSession,
            *,
            school_id: int,
            member_id: int,
            include_inactive: bool = True,
            include_roles: bool = True,
            lock: bool = False,
    ) -> SchoolStaffMember | None:
        """
        Получить сотрудника по id
        строго внутри указанной школы.

        По умолчанию возвращает также
        неактивного сотрудника.

        include_inactive=False:
            вернуть только активного сотрудника.

        Роли подгружаются через selectinload.
        """

        stmt = (
            select(
                SchoolStaffMember
            )
            .where(
                SchoolStaffMember.school_id
                == school_id,

                SchoolStaffMember.id
                == member_id,
            )
            .options(raiseload('*'))
        )
        if include_roles:
            stmt = stmt.options(selectinload(SchoolStaffMember.roles.and_(SchoolStaffRole.school_id == school_id)))
        if lock:
            stmt = stmt.with_for_update(of=SchoolStaffMember)

        if not include_inactive:
            stmt = stmt.where(
                SchoolStaffMember.is_active
                .is_(True)
            )

        result = await db.execute(
            stmt
        )

        return result.scalar_one_or_none()

    # ---------------------------
    # 🔹 Быстрый метод для задач (ОЧЕНЬ ВАЖНЫЙ)
    # ---------------------------
    @staticmethod
    async def get_active_role_ids_by_user_id(
        db: AsyncSession,
        *,
        user_id: int,
    ) -> list[int]:
        """
        Возвращает id активных ролей сотрудника по user_id.

        Используется:
        - в задачах
        - в отчетах
        - в быстрых списках

        Почему отдельный метод:
        - НЕ загружает SchoolStaffMember
        - НЕ тянет relationship
        - работает быстрее на больших данных
        """

        stmt = (
            select(SchoolStaffRole.id)
            .join(
                SchoolStaffMember,
                SchoolStaffMember.id == SchoolStaffRole.staff_member_id,
            )
            .join(
                User,
                User.staff_member_id == SchoolStaffMember.id,
            )
            .where(
                User.id == user_id,
                User.school_id == SchoolStaffMember.school_id,
                SchoolStaffRole.school_id == SchoolStaffMember.school_id,
                SchoolStaffMember.is_active.is_(True),
                SchoolStaffRole.is_active.is_(True),
            )
            .order_by(SchoolStaffRole.id.asc())
        )

        result = await db.execute(stmt)
        return [row[0] for row in result.all()]

    # ---------------------------
    # 🔹 Получить по ИИН
    # ---------------------------
    @staticmethod
    async def get_member_by_iin(
        db: AsyncSession,
        *,
        school_id: int,
        iin: str,
    ) -> SchoolStaffMember | None:
        """
        Получить сотрудника по ИИН.
        """
        stmt = select(SchoolStaffMember).where(
            SchoolStaffMember.school_id == school_id,
            SchoolStaffMember.iin == iin,
        )

        stmt = stmt.options(raiseload('*'))
        result = await db.execute(stmt)
        return result.scalars().first()

    # ---------------------------
    # 🔹 Создание сотрудника
    # ---------------------------
    @staticmethod
    async def create_member(
        db: AsyncSession,
        *,
        school_id: int,
        full_name: str,
        iin: str,
        position_text: str,
        **fields,
    ) -> SchoolStaffMember:
        """
        Создает нового сотрудника.
        """
        member = SchoolStaffMember(
            school_id=school_id,
            full_name=full_name.strip(),
            iin=iin.strip(),
            position_text=position_text,
            **fields,
        )

        db.add(member)
        await db.flush()  # получить id

        return member

    # ---------------------------
    # 🔹 Установка ролей сотрудника
    # ---------------------------
    @staticmethod
    async def set_member_roles(
        db: AsyncSession,
        *,
        school_id: int,
        member_id: int,
        roles: list[tuple[ResponsibleRole, str]],
    ):
        """
        Обновляет активный набор ролей, сохраняя ID и ссылки назначений.
        Удалённые из набора роли становятся неактивными.
        """

        normalized = [r if isinstance(r, dict) else {'role': r[0], 'context': r[1]} for r in roles]
        await SchoolStaffRoleRepo.replace_active(db, school_id=school_id, member_id=member_id, roles=normalized)

    # ---------------------------
    # 🔹 Уволить сотрудника
    # ---------------------------
    @staticmethod
    async def dismiss_member(
        db: AsyncSession,
        *,
        school_id: int,
        member_id: int,
    ):
        """
        Делает сотрудника неактивным.
        """
        await db.execute(
            update(SchoolStaffMember)
            .where(
                SchoolStaffMember.school_id == school_id,
                SchoolStaffMember.id == member_id,
            )
            .values(is_active=False)
        )

    # ---------------------------
    # 🔹 Получить всех сотрудников школы (легкий вариант)
    # ---------------------------
    @staticmethod
    async def get_school_staff_members(
        db: AsyncSession,
        *,
        school_id: int,
    ):
        """
        Возвращает список сотрудников без ролей.

        Используется:
        - для dropdown
        - для control_flow
        """
        stmt = (
            select(SchoolStaffMember)
            .where(SchoolStaffMember.school_id == school_id)
            .options(raiseload('*'))
            .order_by(SchoolStaffMember.full_name.asc())
        )

        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def list_member_cards(db, *, school_id: int):
        """Two narrow Core batches; no ORM relationship graph for the list page."""
        M, R = SchoolStaffMember.__table__, SchoolStaffRole.__table__
        rows = (await db.execute(select(M.c.id, M.c.school_id, M.c.full_name,
            M.c.iin, M.c.position_text, M.c.is_active).where(M.c.school_id == school_id)
            .order_by(M.c.is_active.desc(), M.c.full_name, M.c.id))).mappings().all()
        if not rows:
            return []
        members = {r['id']: SimpleNamespace(**r, roles=[]) for r in rows}
        roles = (await db.execute(select(R.c.id, R.c.staff_member_id, R.c.role,
            R.c.role_context, R.c.is_active).join(M, M.c.id == R.c.staff_member_id)
            .where(R.c.school_id == school_id, M.c.school_id == school_id)
            .order_by(R.c.id))).mappings()
        for role in roles:
            members[role['staff_member_id']].roles.append(SimpleNamespace(**role))
        return list(members.values())


class SchoolStaffRoleRepo:
    # ---------------------------
    # 🔹 Список активных ролей сотрудника
    # ---------------------------
    @staticmethod
    async def list_by_member(
        db: AsyncSession,
        *,
        school_id: int,
        member_id: int,
    ) -> list[SchoolStaffRole]:
        """
        Возвращает активные роли конкретного сотрудника в школе.
        Используется при редактировании ролей.
        """
        stmt = (
            select(SchoolStaffRole)
            .options(raiseload('*'))
            .where(
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.staff_member_id == member_id,
                SchoolStaffRole.is_active.is_(True),
            )
        )
        result = await db.scalars(stmt)
        return list(result.all())

    # ---------------------------
    # 🔹 Удалить все роли сотрудника
    # ---------------------------
    @staticmethod
    async def delete_by_member(
        db: AsyncSession,
        *,
        school_id: int,
        member_id: int,
    ) -> None:
        """
        Удаляет все роли сотрудника в рамках школы.
        Обычно вызывается перед полной заменой ролей.
        """
        await db.execute(
            delete(SchoolStaffRole).where(
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.staff_member_id == member_id,
            )
        )

    # ---------------------------
    # 🔹 Добавить несколько ролей сотруднику
    # ---------------------------
    @staticmethod
    async def add_many(
        db: AsyncSession,
        *,
        school_id: int,
        member_id: int,
        roles: list[dict[str, str]],
    ) -> None:
        """
        Добавляет сотруднику набор ролей.

        Ожидает список словарей вида:
        {"role": "<enum value>", "context": "<text>"}
        """
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

    # ---------------------------
    # 🔹 Получить всех держателей конкретной роли
    # ---------------------------
    @staticmethod
    async def list_holders_for_role(
        db: AsyncSession,
        *,
        school_id: int,
        role: ResponsibleRole,
    ) -> list[SchoolStaffRole]:
        """
        Возвращает все активные role-records по указанной роли.
        Подгружает staff_member, потому что сервису нужен full_name.
        """
        stmt = (
            select(SchoolStaffRole)
            .options(raiseload('*'))
            .where(
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.role == role,
                SchoolStaffRole.is_active.is_(True),
            )
            .join(SchoolStaffMember, SchoolStaffMember.id == SchoolStaffRole.staff_member_id)
            .where(SchoolStaffMember.school_id == school_id, SchoolStaffMember.is_active.is_(True))
            .options(selectinload(SchoolStaffRole.staff_member).raiseload('*'))
        )
        result = await db.scalars(stmt)
        return list(result.all())


    @staticmethod
    async def replace_active(db, *, school_id: int, member_id: int, roles):
        """Serialize by member and preserve role IDs referenced by existing tasks."""
        from fastapi import HTTPException
        R, M = SchoolStaffRole.__table__, SchoolStaffMember.__table__
        wanted = {}
        for row in roles:
            role = ResponsibleRole(row['role'])
            context = str(row.get('context') or '').strip()
            if len(context) > 200:
                raise HTTPException(400, 'Контекст роли: не более 200 символов')
            wanted[(role, context)] = dict(school_id=school_id, staff_member_id=member_id,
                role=role, role_context=context, is_active=True)
        member = (await db.execute(select(M.c.id).where(M.c.school_id == school_id,
            M.c.id == member_id).with_for_update())).scalar_one_or_none()
        if member is None:
            raise HTTPException(404, 'Сотрудник не найден')
        existing = (await db.execute(select(R.c.id, R.c.role, R.c.role_context, R.c.is_active)
            .where(R.c.school_id == school_id, R.c.staff_member_id == member_id).order_by(R.c.id))).mappings().all()
        by_key = {}
        deactivate, reactivate = [], []
        for row in existing:
            key = (row['role'], row['role_context'] or '')
            by_key.setdefault(key, []).append(row)
            if row['is_active'] and key not in wanted:
                deactivate.append(row['id'])
        additions = []
        for key, values in wanted.items():
            matches = by_key.get(key, [])
            if any(row['is_active'] for row in matches):
                continue
            if matches:
                reactivate.append(matches[0]['id'])
            else:
                additions.append(values)
        scope = (R.c.school_id == school_id, R.c.staff_member_id == member_id)
        if deactivate:
            await db.execute(update(R).where(*scope, R.c.id.in_(deactivate)).values(is_active=False))
        if reactivate:
            await db.execute(update(R).where(*scope, R.c.id.in_(reactivate)).values(is_active=True))
        if additions:
            await db.execute(insert(R), additions)
