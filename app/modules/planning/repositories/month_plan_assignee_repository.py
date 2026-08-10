# app/modules/planning/repositories/month_plan_assignee_repository.py

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, selectinload

from app.modules.planning.enums import (
    AssignmentKind,
    ResponsibleRole,
)
from app.modules.planning.models_month_plan import (
    SchoolMonthPlan,
    SchoolMonthPlanItem,
    SchoolMonthPlanItemAssignee,
)
from app.modules.planning.models_school import (
    SchoolPlan,
    SchoolPlanRow11,
    SchoolPlanRow11Assignee,
)
from app.modules.staff.models_staff_school import (
    SchoolStaffMember,
    SchoolStaffRole,
)
from app.modules.users.models import User


class SchoolMonthPlanAssigneeRepo:
    @staticmethod
    async def get_month_item_with_row11(
        db: AsyncSession,
        *,
        month_item_id: int,
    ) -> SchoolMonthPlanItem | None:
        """
        Получить задачу месячного плана вместе с данными
        строки годового плана.
        """

        stmt = (
            select(SchoolMonthPlanItem)
            .options(
                selectinload(
                    SchoolMonthPlanItem.source_row11
                ).selectinload(
                    SchoolPlanRow11.direction
                ),
                selectinload(
                    SchoolMonthPlanItem.source_row11
                ).selectinload(
                    SchoolPlanRow11.role_assignments
                ),
                selectinload(
                    SchoolMonthPlanItem.source_row11
                ).selectinload(
                    SchoolPlanRow11.assignees
                ).selectinload(
                    SchoolPlanRow11Assignee.staff_member
                ),
            )
            .where(
                SchoolMonthPlanItem.id == month_item_id
            )
        )

        result = await db.execute(stmt)
        return result.scalars().unique().one_or_none()

    @staticmethod
    async def get_month_item_for_school_with_row11(
        db: AsyncSession,
        *,
        month_item_id: int,
        school_id: int,
    ) -> SchoolMonthPlanItem | None:
        """
        Получить задачу месячного плана только в пределах школы.

        Одним запросом проверяется цепочка:
        month_item -> month_plan -> school_plan -> school_id.

        Relationships для страницы назначения загружаются пакетно.
        """

        stmt = (
            select(SchoolMonthPlanItem)
            .join(SchoolMonthPlanItem.month_plan)
            .join(SchoolMonthPlan.school_plan)
            .options(
                selectinload(
                    SchoolMonthPlanItem.month_plan
                ),
                selectinload(
                    SchoolMonthPlanItem.source_row11
                ).selectinload(
                    SchoolPlanRow11.direction
                ),
                selectinload(
                    SchoolMonthPlanItem.source_row11
                ).selectinload(
                    SchoolPlanRow11.role_assignments
                ),
                selectinload(
                    SchoolMonthPlanItem.source_row11
                ).selectinload(
                    SchoolPlanRow11.assignees
                ).selectinload(
                    SchoolPlanRow11Assignee.staff_member
                ),
            )
            .where(
                SchoolMonthPlanItem.id == month_item_id,
                SchoolPlan.school_id == school_id,
            )
        )

        result = await db.execute(stmt)
        return result.scalars().unique().one_or_none()

    @staticmethod
    async def list_staff_roles_for_row11_roles(
        db: AsyncSession,
        *,
        school_id: int,
        roles: list[ResponsibleRole],
    ) -> list[SchoolStaffRole]:
        """
        Получить активные должностные роли школы,
        соответствующие плановым ответственным ролям.
        """

        if not roles:
            return []

        unique_roles = list(dict.fromkeys(roles))

        stmt = (
            select(SchoolStaffRole)
            .join(SchoolStaffRole.staff_member)
            .options(
                contains_eager(
                    SchoolStaffRole.staff_member
                )
            )
            .where(
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.is_active.is_(True),
                SchoolStaffMember.is_active.is_(True),
                SchoolStaffRole.role.in_(unique_roles),
            )
            .order_by(
                SchoolStaffRole.role.asc(),
                SchoolStaffRole.role_context.asc(),
                SchoolStaffMember.full_name.asc(),
            )
        )

        result = await db.execute(stmt)
        return list(result.scalars().unique().all())

    @staticmethod
    async def list_active_staff_roles_for_school(
        db: AsyncSession,
        *,
        school_id: int,
    ) -> list[SchoolStaffRole]:
        """
        Получить все активные должностные роли активных
        сотрудников школы.

        Используется для выбора дополнительных соисполнителей:
        руководителей МО, классных руководителей, учителей
        и других сотрудников.
        """

        stmt = (
            select(SchoolStaffRole)
            .join(SchoolStaffRole.staff_member)
            .options(
                contains_eager(
                    SchoolStaffRole.staff_member
                )
            )
            .where(
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.is_active.is_(True),
                SchoolStaffMember.is_active.is_(True),
            )
            .order_by(
                SchoolStaffRole.role.asc(),
                SchoolStaffRole.role_context.asc(),
                SchoolStaffMember.full_name.asc(),
            )
        )

        result = await db.execute(stmt)
        return list(result.scalars().unique().all())

    @staticmethod
    async def list_active_staff_roles_by_ids(
        db: AsyncSession,
        *,
        school_id: int,
        staff_role_ids: list[int],
    ) -> list[SchoolStaffRole]:
        """
        Пакетно проверить выбранные staff_role_id.

        Метод нужен при сохранении формы, чтобы не выполнять
        отдельный SQL-запрос для каждого исполнителя.
        """

        if not staff_role_ids:
            return []

        unique_ids = list(dict.fromkeys(staff_role_ids))

        stmt = (
            select(SchoolStaffRole)
            .join(SchoolStaffRole.staff_member)
            .options(
                contains_eager(
                    SchoolStaffRole.staff_member
                )
            )
            .where(
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.id.in_(unique_ids),
                SchoolStaffRole.is_active.is_(True),
                SchoolStaffMember.is_active.is_(True),
            )
        )

        result = await db.execute(stmt)
        return list(result.scalars().unique().all())

    @staticmethod
    async def delete_row11_assignees(
        db: AsyncSession,
        *,
        row11_id: int,
    ) -> None:
        await db.execute(
            delete(SchoolPlanRow11Assignee).where(
                SchoolPlanRow11Assignee.row11_id
                == row11_id
            )
        )

    @staticmethod
    async def add_row11_assignee(
        db: AsyncSession,
        *,
        row11_id: int,
        staff_member_id: int,
        assigned_by_user_id: int | None,
    ) -> SchoolPlanRow11Assignee:
        assignment = SchoolPlanRow11Assignee(
            row11_id=row11_id,
            staff_member_id=staff_member_id,
            assigned_by_user_id=assigned_by_user_id,
        )

        db.add(assignment)
        return assignment

    @classmethod
    async def replace_row11_assignees(
        cls,
        db: AsyncSession,
        *,
        row11_id: int,
        staff_member_ids: list[int],
        assigned_by_user_id: int | None,
    ) -> None:
        await cls.delete_row11_assignees(
            db,
            row11_id=row11_id,
        )

        unique_ids = list(dict.fromkeys(staff_member_ids))

        assignments = [
            SchoolPlanRow11Assignee(
                row11_id=row11_id,
                staff_member_id=staff_member_id,
                assigned_by_user_id=assigned_by_user_id,
            )
            for staff_member_id in unique_ids
        ]

        db.add_all(assignments)

    @staticmethod
    async def list_month_item_assignees(
        db: AsyncSession,
        *,
        month_item_id: int,
    ) -> list[SchoolMonthPlanItemAssignee]:
        stmt = (
            select(SchoolMonthPlanItemAssignee)
            .options(
                selectinload(
                    SchoolMonthPlanItemAssignee.staff_role
                ).selectinload(
                    SchoolStaffRole.staff_member
                )
            )
            .where(
                SchoolMonthPlanItemAssignee.month_item_id
                == month_item_id
            )
            .order_by(
                SchoolMonthPlanItemAssignee.assignment_kind.asc(),
                SchoolMonthPlanItemAssignee.id.asc(),
            )
        )

        result = await db.execute(stmt)
        return list(result.scalars().unique().all())

    @staticmethod
    async def delete_month_item_assignees(
        db: AsyncSession,
        *,
        month_item_id: int,
    ) -> None:
        await db.execute(
            delete(SchoolMonthPlanItemAssignee).where(
                SchoolMonthPlanItemAssignee.month_item_id
                == month_item_id
            )
        )

    @staticmethod
    async def add_month_item_assignee(
        db: AsyncSession,
        *,
        month_item_id: int,
        staff_role_id: int,
        assignment_kind: AssignmentKind,
        assigned_by_user_id: int | None,
    ) -> SchoolMonthPlanItemAssignee:
        assignment = SchoolMonthPlanItemAssignee(
            month_item_id=month_item_id,
            staff_role_id=staff_role_id,
            assignment_kind=assignment_kind,
            assigned_by_user_id=assigned_by_user_id,
        )

        db.add(assignment)
        return assignment

    @classmethod
    async def replace_month_item_assignees(
        cls,
        db: AsyncSession,
        *,
        month_item_id: int,
        assignees: list[tuple[int, AssignmentKind]],
        assigned_by_user_id: int | None,
    ) -> None:
        """
        Полностью заменить назначения месячной задачи.

        Ожидается:
        - ровно один PRIMARY;
        - любое количество CO_EXECUTOR.

        Бизнес-проверка количества PRIMARY выполняется в сервисе.
        Репозиторий только сохраняет переданный набор.
        """

        await cls.delete_month_item_assignees(
            db,
            month_item_id=month_item_id,
        )

        unique_by_role: dict[
            int,
            AssignmentKind,
        ] = {}

        for staff_role_id, assignment_kind in assignees:
            if staff_role_id not in unique_by_role:
                unique_by_role[staff_role_id] = assignment_kind

        assignments = [
            SchoolMonthPlanItemAssignee(
                month_item_id=month_item_id,
                staff_role_id=staff_role_id,
                assignment_kind=assignment_kind,
                assigned_by_user_id=assigned_by_user_id,
            )
            for staff_role_id, assignment_kind
            in unique_by_role.items()
        ]

        db.add_all(assignments)
        await db.flush()

    @staticmethod
    async def set_month_item_responsible(
        db: AsyncSession,
        *,
        month_item_id: int,
        responsible_role: ResponsibleRole | None,
        responsible_user_id: int | None,
    ) -> None:
        """
        Поддержка старых полей SchoolMonthPlanItem.

        Новым источником истины является
        SchoolMonthPlanItemAssignee.assignment_kind.
        """

        item = await db.scalar(
            select(SchoolMonthPlanItem).where(
                SchoolMonthPlanItem.id == month_item_id
            )
        )

        if item is None:
            raise ValueError(
                "Задача месячного плана не найдена"
            )

        item.responsible_role = responsible_role
        item.responsible_user_id = responsible_user_id

        await db.flush()

    @staticmethod
    async def get_user_id_by_staff_member_id(
        db: AsyncSession,
        *,
        staff_member_id: int,
    ) -> int | None:
        stmt = select(User.id).where(
            User.staff_member_id == staff_member_id
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()
