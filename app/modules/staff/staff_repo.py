# app/modules/staff/staff_repo.py

# app/modules/staff/staff_repo.py

from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
            .options(selectinload(SchoolStaffMember.roles))
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
    ) -> SchoolStaffMember | None:
        """
        Возвращает сотрудника по id внутри школы.

        Подгружает роли.
        """
        stmt = (
            select(SchoolStaffMember)
            .where(
                SchoolStaffMember.school_id == school_id,
                SchoolStaffMember.id == member_id,
            )
            .options(selectinload(SchoolStaffMember.roles))
        )

        result = await db.execute(stmt)
        return result.scalars().first()

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
        Полностью заменяет роли сотрудника.

        Сначала удаляет старые, затем добавляет новые.
        """

        await db.execute(
            delete(SchoolStaffRole).where(
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.staff_member_id == member_id,
            )
        )

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
            .order_by(SchoolStaffMember.full_name.asc())
        )

        result = await db.execute(stmt)
        return result.scalars().all()


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
            .where(
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.role == role,
                SchoolStaffRole.is_active.is_(True),
            )
            .options(selectinload(SchoolStaffRole.staff_member))
        )
        result = await db.scalars(stmt)
        return list(result.all())
