# app/modules/planning/services/month_plan_assignee_service.py

from __future__ import annotations

from collections import defaultdict

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import AssignmentKind, ResponsibleRole
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

        has_deadline = (
            week_of_month is not None
            and planned_start is not None
            and planned_end is not None
        )

        direction = getattr(row11, "direction", None)

        return MonthItemAssigneePageDTO(
            month_item_id=item.id,
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
                is_included
                and has_deadline
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
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            month_item_id: int,
            primary_staff_role_id: int | None,
            co_executor_staff_role_ids: list[int] | None,
            assigned_by_user_id: int | None,
    ) -> tuple[int, int]:
        """
        Сохранить основного исполнителя и соисполнителей.

        Возвращает:
            tuple[int, int]:
            - номер месяца;
            - id годового плана.

        Эти данные используются маршрутом для возврата
        на страницу месячного плана.
        """

        item = (
            await SchoolMonthPlanAssigneeRepo
            .get_month_item_for_school_with_row11(
                db,
                month_item_id=month_item_id,
                school_id=school_id,
            )
        )

        if item is None or item.source_row11 is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Задача месячного плана не найдена.",
            )

        month = item.month_plan.month
        school_plan_id = item.month_plan.school_plan_id

        cls._validate_item_can_be_assigned(item)

        row11 = item.source_row11

        role_assignments = list(
            getattr(row11, "role_assignments", None) or []
        )

        allowed_primary_roles = cls._unique_responsible_roles(
            assignment.role
            for assignment in role_assignments
            if getattr(assignment, "role", None) is not None
        )

        if not allowed_primary_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Для задачи не определены ответственные роли "
                    "в годовом плане."
                ),
            )

        primary_candidates = (
            await SchoolMonthPlanAssigneeRepo
            .list_staff_roles_for_row11_roles(
                db,
                school_id=school_id,
                roles=allowed_primary_roles,
            )
        )

        primary_candidate_map = {
            staff_role.id: staff_role
            for staff_role in primary_candidates
        }

        if primary_staff_role_id is None:
            if len(primary_candidates) == 1:
                primary_staff_role_id = primary_candidates[0].id
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Необходимо выбрать основного исполнителя.",
                )

        primary_staff_role = primary_candidate_map.get(
            primary_staff_role_id
        )

        if primary_staff_role is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Основной исполнитель должен соответствовать "
                    "ответственной роли годового плана и быть "
                    "активным сотрудником этой школы."
                ),
            )

        normalized_co_executor_ids = cls._normalize_ids(
            co_executor_staff_role_ids or []
        )

        normalized_co_executor_ids.discard(
            primary_staff_role_id
        )

        selected_role_ids = {
            primary_staff_role_id,
            *normalized_co_executor_ids,
        }

        selected_staff_roles = (
            await SchoolMonthPlanAssigneeRepo
            .list_active_staff_roles_by_ids(
                db,
                school_id=school_id,
                staff_role_ids=sorted(selected_role_ids),
            )
        )

        selected_role_map = {
            staff_role.id: staff_role
            for staff_role in selected_staff_roles
        }

        missing_role_ids = (
                selected_role_ids
                - set(selected_role_map)
        )

        if missing_role_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Один или несколько выбранных сотрудников "
                    "не найдены, неактивны или не принадлежат школе."
                ),
            )

        primary_staff_member_id = (
            primary_staff_role.staff_member_id
        )

        unique_co_executor_ids: list[int] = []

        seen_staff_member_ids: set[int] = {
            primary_staff_member_id
        }

        for staff_role_id in sorted(
                normalized_co_executor_ids
        ):
            staff_role = selected_role_map[staff_role_id]
            staff_member_id = staff_role.staff_member_id

            if staff_member_id in seen_staff_member_ids:
                continue

            seen_staff_member_ids.add(staff_member_id)
            unique_co_executor_ids.append(staff_role_id)

        assignments: list[
            tuple[int, AssignmentKind]
        ] = [
            (
                primary_staff_role_id,
                AssignmentKind.PRIMARY,
            )
        ]

        assignments.extend(
            (
                staff_role_id,
                AssignmentKind.CO_EXECUTOR,
            )
            for staff_role_id in unique_co_executor_ids
        )

        await (
            SchoolMonthPlanAssigneeRepo
            .replace_month_item_assignees(
                db,
                month_item_id=month_item_id,
                assignees=assignments,
                assigned_by_user_id=assigned_by_user_id,
            )
        )

        responsible_user_id = (
            await SchoolMonthPlanAssigneeRepo
            .get_user_id_by_staff_member_id(
                db,
                staff_member_id=primary_staff_member_id,
            )
        )

        await (
            SchoolMonthPlanAssigneeRepo
            .set_month_item_responsible(
                db,
                month_item_id=month_item_id,
                responsible_role=primary_staff_role.role,
                responsible_user_id=responsible_user_id,
            )
        )

        await db.flush()

        return month, school_plan_id

    @staticmethod
    def _validate_item_can_be_assigned(item) -> None:
        if not bool(getattr(item, "is_included", False)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Нельзя назначить исполнителей задаче, "
                    "которая не включена в месячный план."
                ),
            )

        if (
            getattr(item, "week_of_month", None) is None
            or getattr(item, "planned_start", None) is None
            or getattr(item, "planned_end", None) is None
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Перед назначением исполнителей необходимо "
                    "определить неделю и сроки выполнения задачи."
                ),
            )

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

            group_key = (role_code, role_context)
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
                if participant.assignment_kind
                == AssignmentKind.PRIMARY.value
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
            if getattr(assignment, "assignment_kind", None)
            == AssignmentKind.CO_EXECUTOR
        }

    @staticmethod
    def _normalize_ids(values: list[int]) -> set[int]:
        normalized: set[int] = set()

        for value in values:
            try:
                staff_role_id = int(value)
            except (TypeError, ValueError):
                continue

            if staff_role_id > 0:
                normalized.add(staff_role_id)

        return normalized

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
