from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, contains_eager

from app.modules.planning.enums import ResponsibleRole, AssignmentKind
from app.modules.planning.models_month_plan import SchoolMonthPlanItem, SchoolMonthPlanItemAssignee
from app.modules.planning.models_school import SchoolPlanRow11, SchoolPlanRow11Assignee
from app.modules.staff.models_staff_school import SchoolStaffRole, SchoolStaffMember


class SchoolMonthPlanAssigneeRepo:
    # Получить item месячного плана вместе с source_row11
    @staticmethod
    async def get_month_item_with_row11(
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> SchoolMonthPlanItem | None:
        res = await db.execute(
            select(SchoolMonthPlanItem)
            .options(
                selectinload(SchoolMonthPlanItem.source_row11)
                .selectinload(SchoolPlanRow11.direction),

                selectinload(SchoolMonthPlanItem.source_row11)
                .selectinload(SchoolPlanRow11.role_assignments),

                selectinload(SchoolMonthPlanItem.source_row11)
                .selectinload(SchoolPlanRow11.assignees)
                .selectinload(SchoolPlanRow11Assignee.staff_member),
            )
            .where(SchoolMonthPlanItem.id == month_item_id)
        )
        return res.scalar_one_or_none()

    # Получить доступных сотрудников школы по ролям
    @staticmethod
    async def list_staff_roles_for_row11_roles(
            db: AsyncSession,
            *,
            school_id: int,
            roles: list[ResponsibleRole],
    ) -> list[SchoolStaffRole]:
        if not roles:
            return []

        unique_roles = list(dict.fromkeys(roles))

        res = await db.execute(
            select(SchoolStaffRole)
            .join(SchoolStaffRole.staff_member)
            .options(
                contains_eager(SchoolStaffRole.staff_member)
            )
            .where(
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.is_active.is_(True),
                SchoolStaffRole.role.in_(unique_roles),
            )
            .order_by(
                SchoolStaffRole.role.asc(),
                SchoolStaffRole.role_context.asc(),
                SchoolStaffMember.full_name.asc(),
            )
        )

        return list(res.scalars().unique().all())

    # Удалить текущие назначения по задаче
    @staticmethod
    async def delete_row11_assignees(
            db: AsyncSession,
            *,
            row11_id: int,
    ) -> None:
        await db.execute(
            delete(SchoolPlanRow11Assignee)
            .where(SchoolPlanRow11Assignee.row11_id == row11_id)
        )

    # Добавить новое назначение
    @staticmethod
    async def add_row11_assignee(
            db: AsyncSession,
            *,
            row11_id: int,
            staff_member_id: int,
            assigned_by_user_id: int | None,
    ) -> SchoolPlanRow11Assignee:
        obj = SchoolPlanRow11Assignee(
            row11_id=row11_id,
            staff_member_id=staff_member_id,
            assigned_by_user_id=assigned_by_user_id,
        )
        db.add(obj)
        return obj

    # Полная замена назначений. Это главный метод сохранения.
    @staticmethod
    async def replace_row11_assignees(
            db: AsyncSession,
            *,
            row11_id: int,
            staff_member_ids: list[int],
            assigned_by_user_id: int | None,
    ) -> None:
        await SchoolMonthPlanAssigneeRepo.delete_row11_assignees(
            db,
            row11_id=row11_id,
        )

        unique_ids = list(dict.fromkeys(staff_member_ids))

        for staff_member_id in unique_ids:
            await SchoolMonthPlanAssigneeRepo.add_row11_assignee(
                db,
                row11_id=row11_id,
                staff_member_id=staff_member_id,
                assigned_by_user_id=assigned_by_user_id,
            )

    # --------------------------------------------------
    # МЕСЯЧНЫЕ НАЗНАЧЕНИЯ (новая таблица)
    # --------------------------------------------------

    # Получить назначения задачи месяца
    @staticmethod
    async def list_month_item_assignees(
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> list[SchoolMonthPlanItemAssignee]:

        res = await db.execute(
            select(SchoolMonthPlanItemAssignee)
            .options(
                selectinload(SchoolMonthPlanItemAssignee.staff_role)
                .selectinload(SchoolStaffRole.staff_member)
            )
            .where(
                SchoolMonthPlanItemAssignee.month_item_id == month_item_id
            )
        )

        return list(res.scalars().all())

    # удалить назначения задачи месяца
    @staticmethod
    async def delete_month_item_assignees(
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> None:

        await db.execute(
            delete(SchoolMonthPlanItemAssignee)
            .where(
                SchoolMonthPlanItemAssignee.month_item_id == month_item_id
            )
        )

    # добавить исполнителя задачи месяца
    @staticmethod
    async def add_month_item_assignee(
            db: AsyncSession,
            *,
            month_item_id: int,
            staff_role_id: int,
            assignment_kind: AssignmentKind,
            assigned_by_user_id: int | None,
    ) -> SchoolMonthPlanItemAssignee:

        obj = SchoolMonthPlanItemAssignee(
            month_item_id=month_item_id,
            staff_role_id=staff_role_id,
            assignment_kind=assignment_kind,
            assigned_by_user_id=assigned_by_user_id,
        )

        db.add(obj)
        return obj

    # заменить назначения задачи месяца
    @staticmethod
    async def replace_month_item_assignees(
            db: AsyncSession,
            *,
            month_item_id: int,
            assignees: list[tuple[int, AssignmentKind]],
            assigned_by_user_id: int | None,
    ) -> None:

        await SchoolMonthPlanAssigneeRepo.delete_month_item_assignees(
            db,
            month_item_id=month_item_id,
        )

        unique_assignees: list[tuple[int, AssignmentKind]] = []
        seen: set[int] = set()

        for staff_role_id, assignment_kind in assignees:
            if staff_role_id in seen:
                continue
            seen.add(staff_role_id)
            unique_assignees.append((staff_role_id, assignment_kind))

        for staff_role_id, assignment_kind in unique_assignees:
            await SchoolMonthPlanAssigneeRepo.add_month_item_assignee(
                db,
                month_item_id=month_item_id,
                staff_role_id=staff_role_id,
                assignment_kind=assignment_kind,
                assigned_by_user_id=assigned_by_user_id,
            )


@dataclass
class AssigneeOptionDTO:
    staff_role_id: int
    staff_member_id: int
    full_name: str
    role: str
    role_label: str
    role_context: str | None = None
    checked: bool = False


@dataclass
class ResponsibleBlockDTO:
    role: str
    role_label: str

    # главный ли ответственный
    is_primary: bool = False

    # сотрудники этой роли
    options: list["AssigneeOptionDTO"] = field(default_factory=list)


@dataclass
class MonthItemAssigneePageDTO:
    month_item: SchoolMonthPlanItem
    row11: SchoolPlanRow11
    direction_name: str | None = None
    topic: str | None = None
    goal: str | None = None
    week_of_month: int | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    can_assign: bool = False
    responsible_blocks: list["ResponsibleBlockDTO"] = field(default_factory=list)
    selected_staff_role_ids: list[int] = field(default_factory=list)
