# app/modules/planning/services/month_plan_assignee_service.py

from __future__ import annotations

from collections import defaultdict
from app.modules.planning.repositories.month_correction_repo import MonthCorrectionRepo
from app.modules.planning.services.month_correction_service import MonthCorrectionService, value as enum_value
from app.modules.planning.schemas.month_plan_inputs import MonthItemUpdate
from app.utils.calendar_weeks import month_weeks_grid
from starlette.datastructures import FormData

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import AssignmentKind, ResponsibleRole, PlanStatus
from app.modules.planning.schemas.month_plan_assignee_schemas import (
    AssignedParticipantDTO,
    AssigneeGroupDTO,
    AssigneeOptionDTO,
    MonthItemAssigneePageDTO,
)
from app.modules.planning.repositories.month_plan_assignee_repository import (
    SchoolMonthPlanAssigneeRepo,
)
from app.modules.staff.models_staff_school import SchoolStaffRole


class SchoolMonthPlanAssigneeService:
    """
    Назначение исполнителей задачи месячного плана.

    Правила:
    - ровно один PRIMARY;
    - любое количество CO_EXECUTOR;
    - PRIMARY выбирается по ответственным ролям годового плана;
    - CO_EXECUTOR может быть любой активной ролью сотрудника школы;
    - один сотрудник не назначается дважды через разные staff_role.
    """

    @classmethod
    async def get_assignment_page_data(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            month_item_id: int,
    ) -> MonthItemAssigneePageDTO | None:
        item = await SchoolMonthPlanAssigneeRepo.get_month_item_for_school_with_row11(
            db,
            month_item_id=month_item_id,
            school_id=school_id,
        )
        if item is None or item.source_row11 is None:
            return None

        row11 = item.source_row11
        role_assignments = list(
            getattr(row11, "role_assignments", None) or []
        )
        planned_roles = cls._unique_responsible_roles(
            assignment.role
            for assignment in role_assignments
            if getattr(assignment, "role", None) is not None
        )

        current_assignments = (
            await SchoolMonthPlanAssigneeRepo.list_month_item_assignees(
                db,
                month_item_id=month_item_id,
            )
        )
        selected_primary_role_id = cls._find_primary_staff_role_id(
            current_assignments
        )
        selected_co_executor_role_ids = (
            cls._find_co_executor_staff_role_ids(current_assignments)
        )

        planned_staff_roles: list[SchoolStaffRole] = []
        if planned_roles:
            planned_staff_roles = (
                await SchoolMonthPlanAssigneeRepo
                .list_staff_roles_for_row11_roles(
                    db,
                    school_id=school_id,
                    roles=planned_roles,
                )
            )

        all_school_staff_roles = (
            await SchoolMonthPlanAssigneeRepo
            .list_active_staff_roles_for_school(
                db,
                school_id=school_id,
            )
        )

        if (
                selected_primary_role_id is None
                and not selected_co_executor_role_ids
                and len(planned_staff_roles) == 1
        ):
            selected_primary_role_id = planned_staff_roles[0].id

        primary_groups = cls._build_groups(
            planned_staff_roles,
            selected_primary_staff_role_id=selected_primary_role_id,
            selected_co_executor_staff_role_ids=(
                selected_co_executor_role_ids
            ),
            allow_primary=True,
        )

        planned_co_executor_groups = cls._build_groups(
            planned_staff_roles,
            selected_primary_staff_role_id=selected_primary_role_id,
            selected_co_executor_staff_role_ids=(
                selected_co_executor_role_ids
            ),
            allow_primary=False,
        )

        planned_staff_role_ids = {
            staff_role.id
            for staff_role in planned_staff_roles
        }

        additional_staff_roles = [
            staff_role
            for staff_role in all_school_staff_roles
            if staff_role.id not in planned_staff_role_ids
        ]

        additional_co_executor_groups = cls._build_groups(
            additional_staff_roles,
            selected_primary_staff_role_id=selected_primary_role_id,
            selected_co_executor_staff_role_ids=(
                selected_co_executor_role_ids
            ),
            allow_primary=False,
        )

        assigned_participants = cls._build_assigned_participants(
            current_assignments
        )

        week_of_month = getattr(item, "week_of_month", None)
        planned_start = getattr(item, "planned_start", None)
        planned_end = getattr(item, "planned_end", None)
        is_included = bool(getattr(item, "is_included", False))
        month_plan = getattr(
            item,
            "month_plan",
            None,
        )

        school_plan = (
            getattr(month_plan, "school_plan", None)
            if month_plan is not None
            else None
        )

        is_archived = (
                month_plan is None
                or school_plan is None
                or cls._is_archived(
                    getattr(month_plan, "status", None)) or cls._is_archived(getattr(school_plan, "status", None))
                )

        direction = getattr(row11, "direction", None)

        snapshot = await MonthCorrectionRepo.snapshot(db, school_id=school_id, month_plan_id=item.month_plan_id)

        if snapshot is None:
            return None

        return MonthItemAssigneePageDTO(
            month_item_id=item.id,
            year=month_plan.year,
            plan_revision=MonthCorrectionService.revision(snapshot),
            month=getattr(month_plan, "month", None),
            school_plan_id=getattr(month_plan, "school_plan_id", None),
            is_active_plan=(getattr(month_plan, "status", None) == PlanStatus.ACTIVE),
            row11_id=getattr(row11, "id", None),
            direction_name=(
                    getattr(direction, "short_title", None)
                    or getattr(direction, "title", None)
                    or "—"
            ),
            topic=getattr(row11, "topic", None) or "—",
            goal=getattr(row11, "goal", None) or "—",
            week_of_month=week_of_month,
            planned_start=planned_start,
            planned_end=planned_end,
            is_included=is_included,
            can_assign=(
                    not is_archived
                    and bool(planned_staff_roles)
            ),
            primary_groups=primary_groups,
            planned_co_executor_groups=planned_co_executor_groups,
            additional_co_executor_groups=(
                additional_co_executor_groups
            ),
            assigned_participants=assigned_participants,
            selected_primary_staff_role_id=selected_primary_role_id,
            selected_co_executor_staff_role_ids=sorted(
                selected_co_executor_role_ids
            ),
        )

    @classmethod
    async def save_assignments(
        cls, db: AsyncSession, *, school_id: int, month_item_id: int,
        primary_staff_role_id: int | None, co_executor_staff_role_ids: list[int] | None,
        assigned_by_user_id: int | None, correction_reason: str | None = None,
        plan_revision: str, schedule_week: str = "", audit_out: list | None = None,
        include_in_plan: bool | None = None,
    ) -> tuple[int, int]:
        # Resolve the school boundary before any mutation. The correction service
        # locks and checks the revision again in the same request transaction.
        item = await SchoolMonthPlanAssigneeRepo.get_month_item_for_school_with_row11(
            db, school_id=school_id, month_item_id=month_item_id)
        if item is None or item.source_row11 is None:
            raise HTTPException(404, "Задача не найдена / Тапсырма табылмады")
        data = await MonthCorrectionRepo.snapshot(
            db, school_id=school_id, month_plan_id=item.month_plan_id, lock=True)
        if data is None:
            raise HTTPException(404, "План не найден / Жоспар табылмады")
        record = next((row for row in data['items'] if row['id'] == month_item_id), None)
        if record is None:
            raise HTTPException(404, "Задача не найдена / Тапсырма табылмады")
        weeks = {w.week: w for w in month_weeks_grid(data['plan']['year'], data['plan']['month'])}
        try:
            week = int(schedule_week) if schedule_week else None
        except (ValueError, TypeError):
            raise HTTPException(400, "Выберите неделю / Аптаны таңдаңыз")
        if week is not None and week not in weeks:
            raise HTTPException(400, "Неделя не входит в месяц / Апта айға кірмейді")
        if primary_staff_role_id is None:
            planned = {enum_value(r['role']) for r in data['planned'] if r['item_id'] == month_item_id}
            eligible = [r['id'] for r in data['roles'] if enum_value(r['role']) in planned]
            if len(eligible) == 1:
                primary_staff_role_id = eligible[0]
            else:
                raise HTTPException(400, "Выберите основного исполнителя / Негізгі орындаушыны таңдаңыз")
        prefix = f'item_{month_item_id}_'
        form = FormData([
            ('plan_revision', plan_revision), ('correction_reason', correction_reason or ''),
            (prefix+'primary', str(primary_staff_role_id)),
            *((prefix+'co', str(rid)) for rid in (co_executor_staff_role_ids or [])),
        ])
        selected = weeks.get(week)
        update = MonthItemUpdate(
            item_id=month_item_id, is_included=(record['is_included'] if include_in_plan is None else include_in_plan), notes=record['notes'],
            week_of_month=week, planned_start=selected.start if selected else None,
            planned_end=selected.end if selected else None)
        audit = await MonthCorrectionService.save(
            db, school_id=school_id, month_plan_id=item.month_plan_id,
            school_plan_id=data['plan']['school_plan_id'], month=data['plan']['month'],
            updates=[update], form=form, actor_id=assigned_by_user_id, target_item_id=month_item_id)
        if audit_out is not None:
            audit_out.append(audit)
        return data['plan']['month'], data['plan']['school_plan_id']

    @staticmethod
    def _is_archived(value) -> bool:
        status_value = str(
            getattr(
                value,
                "value",
                value,
            )
        )

        return status_value == PlanStatus.ARCHIVED.value

    @classmethod
    def _build_groups(
            cls,
            staff_roles: list[SchoolStaffRole],
            *,
            selected_primary_staff_role_id: int | None,
            selected_co_executor_staff_role_ids: set[int],
            allow_primary: bool,
    ) -> list[AssigneeGroupDTO]:
        grouped: dict[
            tuple[str, str],
            list[AssigneeOptionDTO],
        ] = defaultdict(list)
        group_labels: dict[tuple[str, str], str] = {}

        for staff_role in staff_roles:
            staff_member = getattr(
                staff_role,
                "staff_member",
                None,
            )
            if staff_member is None:
                continue

            role = getattr(staff_role, "role", None)
            role_code = cls._enum_value(role)
            role_label = cls._enum_label(role)
            role_context = (
                    getattr(staff_role, "role_context", None)
                    or ""
            ).strip()

            group_key = (role_code, role_context if allow_primary else "")
            group_labels[group_key] = role_label

            grouped[group_key].append(
                AssigneeOptionDTO(
                    staff_role_id=staff_role.id,
                    staff_member_id=staff_member.id,
                    full_name=(
                            getattr(staff_member, "full_name", None)
                            or "—"
                    ),
                    role=role_code,
                    role_label=role_label,
                    role_context=role_context,
                    position_text=(
                            getattr(staff_member, "position_text", None)
                            or ""
                    ),
                    subject=(
                            getattr(staff_member, "subject", None)
                            or ""
                    ),
                    selected_as_primary=(
                            allow_primary
                            and staff_role.id
                            == selected_primary_staff_role_id
                    ),
                    selected_as_co_executor=(
                            staff_role.id
                            in selected_co_executor_staff_role_ids
                    ),
                )
            )

        result: list[AssigneeGroupDTO] = []

        for group_key, options in grouped.items():
            role_code, role_context = group_key
            options.sort(
                key=lambda option: (
                        option.full_name or ""
                ).casefold()
            )

            result.append(
                AssigneeGroupDTO(
                    code=(
                        f"{role_code}:{role_context}"
                        if role_context
                        else role_code
                    ),
                    label=group_labels[group_key],
                    role_context=role_context,
                    options=options,
                )
            )

        result.sort(
            key=lambda group: (
                group.label.casefold(),
                group.role_context.casefold(),
            )
        )
        return result

    @classmethod
    def _build_assigned_participants(
            cls,
            assignments,
    ) -> list[AssignedParticipantDTO]:
        participants: list[AssignedParticipantDTO] = []

        for assignment in assignments:
            staff_role = getattr(assignment, "staff_role", None)
            if staff_role is None:
                continue

            staff_member = getattr(staff_role, "staff_member", None)
            if staff_member is None:
                continue

            assignment_kind = getattr(
                assignment,
                "assignment_kind",
                None,
            )

            participants.append(
                AssignedParticipantDTO(
                    staff_role_id=staff_role.id,
                    staff_member_id=staff_member.id,
                    full_name=(
                            getattr(staff_member, "full_name", None)
                            or "—"
                    ),
                    role_label=cls._enum_label(
                        getattr(staff_role, "role", None)
                    ),
                    assignment_kind=cls._enum_value(
                        assignment_kind
                    ),
                    assignment_kind_label=cls._enum_label(
                        assignment_kind
                    ),
                    role_context=(
                            getattr(staff_role, "role_context", None)
                            or ""
                    ).strip(),
                    position_text=(
                            getattr(staff_member, "position_text", None)
                            or ""
                    ),
                )
            )

        participants.sort(
            key=lambda participant: (
                0
                if participant.assignment_kind == AssignmentKind.PRIMARY.value
                else 1,
                participant.full_name.casefold(),
            )
        )
        return participants

    @staticmethod
    def _find_primary_staff_role_id(assignments) -> int | None:
        for assignment in assignments:
            if (
                    getattr(assignment, "assignment_kind", None)
                    == AssignmentKind.PRIMARY
            ):
                return getattr(assignment, "staff_role_id", None)
        return None

    @staticmethod
    def _find_co_executor_staff_role_ids(assignments) -> set[int]:
        return {
            assignment.staff_role_id
            for assignment in assignments
            if getattr(assignment, "assignment_kind", None) == AssignmentKind.CO_EXECUTOR
        }

    @staticmethod
    def _unique_responsible_roles(roles) -> list[ResponsibleRole]:
        result: list[ResponsibleRole] = []
        seen: set[ResponsibleRole] = set()

        for role in roles:
            if role in seen:
                continue

            seen.add(role)
            result.append(role)

        return result

    @staticmethod
    def _enum_value(value) -> str:
        if value is None:
            return ""
        return str(getattr(value, "value", value))

    @staticmethod
    def _enum_label(value) -> str:
        if value is None:
            return "—"

        return str(
            getattr(value, "label_kz", None)
            or getattr(value, "label_ru", None)
            or getattr(value, "label", None)
            or getattr(value, "value", None)
            or value
        )
