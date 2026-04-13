from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import AssignmentKind
from app.modules.planning.ropo_month_plan_assignee import (
    AssigneeOptionDTO,
    ResponsibleBlockDTO,
    MonthItemAssigneePageDTO,
    SchoolMonthPlanAssigneeRepo
)
from app.modules.staff.models_staff_school import SchoolStaffRole


class SchoolMonthPlanAssigneeService:
    # --------------------------------------------------
    # Подготовка страницы назначения исполнителей
    # --------------------------------------------------
    @staticmethod
    async def get_assignment_page_data(
            db: AsyncSession,
            *,
            school_id: int,
            month_item_id: int,
    ) -> MonthItemAssigneePageDTO | None:

        item = await SchoolMonthPlanAssigneeRepo.get_month_item_with_row11(
            db,
            month_item_id=month_item_id,
        )

        if not item or not item.source_row11:
            return None

        row11 = item.source_row11

        # --------------------------------------------------
        # направление
        # --------------------------------------------------
        direction_name = row11.direction.short_title if row11.direction else None

        # --------------------------------------------------
        # тема / цель
        # --------------------------------------------------
        topic = row11.topic if row11.topic else None
        goal = row11.goal if row11.goal else None

        # --------------------------------------------------
        # сроки выполнения
        # --------------------------------------------------
        week_of_month = item.week_of_month
        planned_start = item.planned_start
        planned_end = item.planned_end

        # --------------------------------------------------
        # можно ли назначать
        # --------------------------------------------------
        is_included = item.is_included
        has_deadline = bool(week_of_month) and planned_start is not None and planned_end is not None
        can_assign = is_included and has_deadline

        # --------------------------------------------------
        # роли задачи из row11
        # --------------------------------------------------
        role_assignments = list(row11.role_assignments or [])
        roles = [r.role for r in role_assignments]

        # --------------------------------------------------
        # текущие назначения уже у month_item
        # --------------------------------------------------
        month_item_assignees = await SchoolMonthPlanAssigneeRepo.list_month_item_assignees(
            db,
            month_item_id=month_item_id,
        )

        selected_staff_role_ids = [a.staff_role_id for a in month_item_assignees]

        # --------------------------------------------------
        # сотрудники школы по ролям
        # --------------------------------------------------
        staff_roles: list[SchoolStaffRole] = []

        if roles:
            staff_roles = await SchoolMonthPlanAssigneeRepo.list_staff_roles_for_row11_roles(
                db,
                school_id=school_id,
                roles=roles,
            )

        # --------------------------------------------------
        # группировка сотрудников по роли
        # --------------------------------------------------
        by_role: dict[str, list[SchoolStaffRole]] = {}

        for sr in staff_roles:
            key = sr.role.value
            by_role.setdefault(key, []).append(sr)

        # --------------------------------------------------
        # формируем блоки ролей
        # --------------------------------------------------
        responsible_blocks: list[ResponsibleBlockDTO] = []

        for resp in role_assignments:
            role_key = resp.role.value
            role_label = getattr(resp.role, "label_kz", resp.role.value)

            block = ResponsibleBlockDTO(
                role=role_key,
                role_label=role_label,
                is_primary=resp.is_primary,
                options=[],
            )

            staff_list = by_role.get(role_key, [])

            for sr in staff_list:
                sm = sr.staff_member
                if not sm:
                    continue

                option = AssigneeOptionDTO(
                    staff_role_id=sr.id,
                    staff_member_id=sm.id,
                    full_name=sm.full_name,
                    role=sr.role.value,
                    role_label=role_label,
                    role_context=(sr.role_context or "").strip(),
                    checked=(sr.id in selected_staff_role_ids),
                )

                block.options.append(option)

            block.options.sort(key=lambda x: x.full_name.lower() if x.full_name else "")
            responsible_blocks.append(block)

        # --------------------------------------------------
        # DTO
        # --------------------------------------------------
        return MonthItemAssigneePageDTO(
            month_item=item,
            row11=row11,
            direction_name=direction_name,
            topic=topic,
            goal=goal,
            week_of_month=week_of_month,
            planned_start=planned_start,
            planned_end=planned_end,
            can_assign=can_assign,
            responsible_blocks=responsible_blocks,
            selected_staff_role_ids=selected_staff_role_ids,
        )

    # --------------------------------------------------
    # Сохранение назначений month_item
    # Главный определяется порядком role_assignments/is_primary на странице,
    # а в таблицу month_item_assignees пишем:
    #   - PRIMARY для ролей из primary-блока
    #   - CO_EXECUTOR для остальных
    # --------------------------------------------------
    @staticmethod
    async def save_assignments(
            db: AsyncSession,
            *,
            school_id: int,
            month_item_id: int,
            selected_staff_role_ids: list[int],
            primary_staff_role_id: int | None,
            assigned_by_user_id: int | None,
    ) -> bool:
        item = await SchoolMonthPlanAssigneeRepo.get_month_item_with_row11(
            db,
            month_item_id=month_item_id,
        )
        if not item or not item.source_row11:
            return False

        row11 = item.source_row11
        role_assignments = list(row11.role_assignments or [])
        roles = [r.role for r in role_assignments]

        if not roles:
            await SchoolMonthPlanAssigneeRepo.replace_month_item_assignees(
                db,
                month_item_id=month_item_id,
                assignees=[],
                assigned_by_user_id=assigned_by_user_id,
            )

            await SchoolMonthPlanAssigneeRepo.set_month_item_responsible(
                db,
                month_item_id=month_item_id,
                responsible_role=None,
                responsible_user_id=None,
            )
            return True

        staff_roles = await SchoolMonthPlanAssigneeRepo.list_staff_roles_for_row11_roles(
            db,
            school_id=school_id,
            roles=roles,
        )

        staff_role_map = {sr.id: sr for sr in staff_roles}

        unique_selected_ids: list[int] = []
        seen: set[int] = set()

        for x in selected_staff_role_ids:
            if x in staff_role_map and x not in seen:
                unique_selected_ids.append(x)
                seen.add(x)

        if not unique_selected_ids:
            await SchoolMonthPlanAssigneeRepo.replace_month_item_assignees(
                db,
                month_item_id=month_item_id,
                assignees=[],
                assigned_by_user_id=assigned_by_user_id,
            )

            await SchoolMonthPlanAssigneeRepo.set_month_item_responsible(
                db,
                month_item_id=month_item_id,
                responsible_role=None,
                responsible_user_id=None,
            )
            return True

        if len(unique_selected_ids) == 1:
            primary_staff_role_id = unique_selected_ids[0]

        if primary_staff_role_id is None:
            raise HTTPException(
                status_code=400,
                detail="Не выбран главный ответственный",
            )

        if primary_staff_role_id not in unique_selected_ids:
            raise HTTPException(
                status_code=400,
                detail="Главный ответственный должен входить в список выбранных сотрудников",
            )

        assignees: list[tuple[int, AssignmentKind]] = []

        for staff_role_id in unique_selected_ids:
            kind = (
                AssignmentKind.PRIMARY
                if staff_role_id == primary_staff_role_id
                else AssignmentKind.CO_EXECUTOR
            )
            assignees.append((staff_role_id, kind))

        await SchoolMonthPlanAssigneeRepo.replace_month_item_assignees(
            db,
            month_item_id=month_item_id,
            assignees=assignees,
            assigned_by_user_id=assigned_by_user_id,
        )

        primary_sr = staff_role_map[primary_staff_role_id]

        responsible_user_id = await SchoolMonthPlanAssigneeRepo.get_user_id_by_staff_member_id(
            db,
            staff_member_id=primary_sr.staff_member_id,
        )

        await SchoolMonthPlanAssigneeRepo.set_month_item_responsible(
            db,
            month_item_id=month_item_id,
            responsible_role=primary_sr.role,
            responsible_user_id=responsible_user_id,
        )
        return True
