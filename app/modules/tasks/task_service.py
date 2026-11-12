# app/modules/tasks/task_service.py
from __future__ import annotations

import logging

from collections import defaultdict
from datetime import date
from typing import cast

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import AssignmentKind, PlanItemStatus
from app.modules.planning.services.month_plan_notification_service import MonthPlanNotificationService
from app.modules.reports.rules.control_flow import build_control_flow_for_ui
from app.modules.reports.repositories.execution_repo import ExecutionRepo
from app.modules.reports.repositories.report_type_repo import ReportTypeRepo
from app.modules.reports.report_repo import ReportRepo
from app.modules.reports.report_schemas import (
    CurrentDraftDTO,
    ExecutionFormDTO,
    StaffExecutionPagePayloadDTO,
    StaffExecutionTaskDTO,
)
from app.modules.reports.repositories.report_assignment_repo import ReportAssignmentRepo
from app.modules.staff.staff_repo import SchoolStaffRepo
from app.modules.tasks.schemas import MyTaskDTO, CoExecutorTaskDTO
from app.modules.tasks.task_repo import StaffTasksRepo
from app.modules.tasks.task_display import review_place_text, execution_fields
from app.modules.users.models import User

logger = logging.getLogger(__name__)


class StaffTasksService:
    """
    Сервис staff-domain для:
    - списка моих задач
    - принятия задачи в работу
    - сборки payload страницы исполнения task_execute.html

    Важно:
    - repo отвечает за чтение ORM-моделей
    - service отвечает за orchestration и сборку DTO
    """

    @staticmethod
    async def get_my_tasks_page(
            db: AsyncSession,
            *,
            user: User,
            month: int,
    ) -> tuple[list[MyTaskDTO], list[CoExecutorTaskDTO]]:
        """
        Получить задачи сотрудника за выбранный месяц,
        разделённые по виду назначения.

        Возвращает:

            primary_tasks, co_executor_tasks

        Источник истины для роли сотрудника:
        SchoolMonthPlanItemAssignee.assignment_kind.

        PRIMARY:
        - получает MyTaskDTO;
        - принимает задачу;
        - управляет выполнением задачи.

        CO_EXECUTOR:
        - получает CoExecutorTaskDTO;
        - видит PRIMARY;
        - получает доступ только после подготовки задачи;
        - работает только с назначенными ему отчётами.
        """

        school_id = getattr(user, "school_id", None)
        user_id = getattr(user, "id", None)

        if school_id is None or user_id is None:
            return [], []

        # =========================================================
        # STAFF ROLES
        # =========================================================

        role_ids = (
            await SchoolStaffRepo
            .get_active_role_ids_by_user_id(
                db,
                user_id=cast(int, user_id),
            )
        )

        if not role_ids:
            return [], []

        staff_role_ids = {
            int(role_id)
            for role_id in role_ids
        }

        # =========================================================
        # TASKS
        # =========================================================

        tasks = await StaffTasksRepo.list_tasks_for_staff(
            db,
            school_id=cast(int, school_id),
            staff_role_ids=list(staff_role_ids),
            month=month,
        )

        today = date.today()

        primary_tasks: list[MyTaskDTO] = []
        co_executor_tasks: list[CoExecutorTaskDTO] = []

        # =========================================================
        # BUILD DTOs
        # =========================================================

        for task in tasks:

            assignment_kind = (
                StaffTasksService
                ._resolve_staff_assignment_kind(
                    task,
                    staff_role_ids=staff_role_ids,
                )
            )

            if assignment_kind is None:
                logger.warning(
                    "Task %s returned for user %s, but no matching "
                    "assignment was found for staff roles %s",
                    getattr(task, "id", None),
                    user_id,
                    sorted(staff_role_ids),
                )
                continue

            # -----------------------------------------------------
            # PRIMARY
            # -----------------------------------------------------

            if assignment_kind == AssignmentKind.PRIMARY:
                task_dto = (
                    StaffTasksService
                    ._build_task_list_dto(
                        task,
                        today=today,
                        month=month,
                    )
                )

                primary_tasks.append(
                    task_dto
                )

                continue

            # -----------------------------------------------------
            # CO-EXECUTOR
            # -----------------------------------------------------

            if assignment_kind == AssignmentKind.CO_EXECUTOR:
                task_dto = (
                    await StaffTasksService
                    ._build_co_executor_task_dto(
                        db,
                        task=task,
                        school_id=cast(int, school_id),
                        staff_role_ids=staff_role_ids,
                        today=today,
                        month=month,
                    )
                )

                co_executor_tasks.append(
                    task_dto
                )

        return (
            primary_tasks,
            co_executor_tasks,
        )

    @staticmethod
    def _resolve_staff_assignment_kind(
            task,
            *,
            staff_role_ids: set[int],
    ) -> AssignmentKind | None:
        """
        Определить вид назначения текущего сотрудника в задаче.

        Репозиторий должен заранее загрузить коллекцию:

            SchoolMonthPlanItem.assignees
        """
        task_state = getattr(task, "__dict__", {})
        assignees = task_state.get("assignees")

        if assignees is None:
            logger.error(
                "Relation SchoolMonthPlanItem.assignees is not loaded "
                "for task %s",
                getattr(task, "id", None),
            )
            return None

        matched_kinds: set[AssignmentKind] = set()

        for assignee in assignees:
            staff_role_id = getattr(
                assignee,
                "staff_role_id",
                None,
            )

            if staff_role_id is None:
                continue

            if int(staff_role_id) not in staff_role_ids:
                continue

            raw_kind = getattr(
                assignee,
                "assignment_kind",
                None,
            )

            normalized_kind = (
                StaffTasksService._normalize_assignment_kind(
                    raw_kind
                )
            )

            if normalized_kind is not None:
                matched_kinds.add(normalized_kind)

        # Защитный приоритет на случай некорректных дублей в БД.
        if AssignmentKind.PRIMARY in matched_kinds:
            return AssignmentKind.PRIMARY

        if AssignmentKind.CO_EXECUTOR in matched_kinds:
            return AssignmentKind.CO_EXECUTOR

        return None

    @staticmethod
    def _normalize_assignment_kind(
            raw_kind,
    ) -> AssignmentKind | None:
        """
        Нормализовать assignment_kind из ORM enum или строки.
        """
        if raw_kind is None:
            return None

        if isinstance(raw_kind, AssignmentKind):
            return raw_kind

        raw_value = getattr(
            raw_kind,
            "value",
            raw_kind,
        )

        try:
            return AssignmentKind(raw_value)
        except (TypeError, ValueError):
            logger.warning(
                "Unknown assignment_kind value: %r",
                raw_kind,
            )
            return None

    @staticmethod
    def _build_task_common_data(
            task,
            *,
            today: date,
    ) -> dict:
        source_row11 = getattr(task, "source_row11", None)

        planned_start = getattr(task, "planned_start", None)
        planned_end = getattr(task, "planned_end", None)

        task_status = StaffTasksService._resolve_status(
            raw_status=getattr(task, "status", None),
            planned_end=planned_end,
            today=today,
        )

        return {
            "month_item_id": int(getattr(task, "id")),
            "week_of_month": getattr(task, "week_of_month", None),
            "planned_start": planned_start,
            "planned_end": planned_end,
            "period_text": StaffTasksService._format_period(
                planned_start,
                planned_end,
            ),
            "topic": (
                    getattr(source_row11, "topic", None)
                    or "—"
            ),
            "goal": (
                    getattr(source_row11, "goal", None)
                    or "—"
            ),
            "control_object": (
                    getattr(source_row11, "control_object", None)
                    or "—"
            ),
            "control_type": (
                    getattr(source_row11, "control_type", None)
                    or "—"
            ),
            "review_place": (
                StaffTasksService._build_review_place_text(task)
            ),
            "status": task_status,
            "status_label": (
                StaffTasksService._status_label(task_status)
            ),
            "status_color": (
                StaffTasksService._status_color(task_status)
            ),
        }

    @staticmethod
    def _build_task_list_dto(
            task,
            *,
            today: date,
            month: int,
    ) -> MyTaskDTO:
        """
        DTO задачи ответственного исполнителя.
        """

        data = StaffTasksService._build_task_common_data(
            task,
            today=today,
        )

        month_item_id = data["month_item_id"]

        has_selected_reports = (
            StaffTasksService
            ._has_loaded_selected_reports(task)
        )

        return MyTaskDTO(
            **data,

            has_selected_reports=has_selected_reports,

            action_kind=(
                StaffTasksService._action_kind(
                    data["status"]
                )
            ),

            action_url=StaffTasksService._action_url(
                task_status=data["status"],
                item_id=month_item_id,
                month=month,
                has_selected_reports=has_selected_reports,
            ),

            action_label=(
                StaffTasksService._action_label(
                    data["status"]
                )
            ),
        )

    @classmethod
    async def _build_co_executor_task_dto(
            cls,
            db: AsyncSession,
            *,
            task,
            school_id: int,
            staff_role_ids: set[int],
            today: date,
            month: int,
    ) -> CoExecutorTaskDTO:
        """
        Сформировать DTO задачи соисполнителя.

        Источники истины:

        - роль соисполнителя:
          SchoolMonthPlanItemAssignee.assignment_kind;

        - ответственный PRIMARY:
          ReportAssignmentRepo.list_executor_choices();

        - доступ к работе:
          наличие отчетов, фактически назначенных
          текущему соисполнителю.

        Для соисполнителя наличие хотя бы одного назначенного отчета
        означает, что ответственный уже сформировал рабочую часть
        алгоритма и выполнил распределение отчетов.
        """

        # =========================================================
        # COMMON TASK DATA
        # =========================================================

        data = cls._build_task_common_data(
            task,
            today=today,
        )

        month_item_id = int(
            data["month_item_id"]
        )

        task_status = str(
            data["status"] or ""
        )

        # =========================================================
        # CURRENT CO-EXECUTOR
        # =========================================================

        current_staff_member_id: int | None = None

        assignees = (
                getattr(task, "assignees", None)
                or []
        )

        for assignee in assignees:
            staff_role_id = getattr(
                assignee,
                "staff_role_id",
                None,
            )

            if staff_role_id is None:
                continue

            if int(staff_role_id) not in staff_role_ids:
                continue

            assignment_kind = (
                cls._normalize_assignment_kind(
                    getattr(
                        assignee,
                        "assignment_kind",
                        None,
                    )
                )
            )

            if (
                    assignment_kind
                    != AssignmentKind.CO_EXECUTOR
            ):
                continue

            staff_role = getattr(
                assignee,
                "staff_role",
                None,
            )

            staff_member = (
                getattr(
                    staff_role,
                    "staff_member",
                    None,
                )
                if staff_role
                else None
            )

            staff_member_id = getattr(
                staff_member,
                "id",
                None,
            )

            if staff_member_id is not None:
                current_staff_member_id = int(
                    staff_member_id
                )
                break

        if current_staff_member_id is None:
            logger.warning(
                "Cannot resolve staff_member_id for co-executor "
                "in task %s; staff_role_ids=%s",
                month_item_id,
                sorted(staff_role_ids),
            )

        # =========================================================
        # PRIMARY EXECUTOR
        # =========================================================

        executors = (
            await ReportAssignmentRepo
            .list_executor_choices(
                db,
                month_item_id=month_item_id,
                school_id=school_id,
            )
        )

        primary_executor = next(
            (
                executor
                for executor in executors
                if executor.is_primary
            ),
            None,
        )

        primary_staff_member_id = (
            primary_executor.staff_member_id
            if primary_executor
            else None
        )

        primary_full_name = (
            primary_executor.full_name
            if primary_executor
            else "Не назначен"
        )

        primary_position_text = (
            primary_executor.position_text
            if primary_executor
            else None
        )

        # =========================================================
        # PRIMARY HAS ACCEPTED TASK
        # =========================================================

        is_accepted = bool(
            task_status
            and task_status
            != PlanItemStatus.TODO.value
        )

        # =========================================================
        # PERSONAL REPORT ASSIGNMENTS
        # =========================================================

        assigned_reports_count = 0

        if current_staff_member_id is not None:
            assigned_reports_count = (
                await ReportAssignmentRepo
                .count_reports_for_staff(
                    db,
                    month_item_id=month_item_id,
                    staff_member_id=current_staff_member_id,
                )
            )

        has_assigned_reports = (
                assigned_reports_count > 0
        )

        # =========================================================
        # EXECUTION ALGORITHM
        # =========================================================

        # Для соисполнителя источником истины является
        # не загруженный execution_data.selected_reports,
        # а фактическое назначение ему отчетов.
        #
        # Если хотя бы один отчет назначен,
        # значит ответственный уже сформировал
        # рабочую часть алгоритма и выполнил распределение.
        has_execution_algorithm = (
            has_assigned_reports
        )

        # =========================================================
        # ACCESS TO REPORTS
        # =========================================================

        can_fill_reports = bool(
            is_accepted
            and has_assigned_reports
        )

        # =========================================================
        # ACTION
        # =========================================================

        action_kind = ""
        action_url = None
        action_label = None
        action_css = None

        if can_fill_reports:
            action_kind = "fill_reports"

            action_url = (
                f"/staff/reports/"
                f"{month_item_id}/templates"
                f"?month={month}"
            )

            action_label = (
                f"Заполнить отчёты "
                f"({assigned_reports_count})"
            )

            action_css = (
                "btn-outline-primary"
            )

        elif not is_accepted:
            action_label = (
                "Ожидание принятия задачи "
                "ответственным"
            )

        elif not has_assigned_reports:
            action_label = (
                "Отчёты вам не назначены"
            )

        # =========================================================
        # DTO
        # =========================================================

        return CoExecutorTaskDTO(
            **data,

            primary_staff_member_id=(
                primary_staff_member_id
            ),
            primary_full_name=(
                primary_full_name
            ),
            primary_position_text=(
                primary_position_text
            ),

            is_accepted=is_accepted,

            has_execution_algorithm=(
                has_execution_algorithm
            ),

            assigned_reports_count=(
                assigned_reports_count
            ),

            has_assigned_reports=(
                has_assigned_reports
            ),

            can_fill_reports=(
                can_fill_reports
            ),

            action_kind=action_kind,
            action_url=action_url,
            action_label=action_label,
            action_css=action_css,
        )

    @staticmethod
    def _build_review_place_text(task) -> str:
        """
        Сформировать строку мест рассмотрения задачи.

        Использует только заранее загруженную коллекцию
        SchoolMonthPlanItem.review_places.
        """
        return review_place_text(task)

    @staticmethod
    def _has_loaded_selected_reports(task) -> bool:
        """
        Проверить наличие выбранных отчетов без запуска lazy SQL.

        Метод читает только уже загруженные ORM-атрибуты. Если
        execution_data или selected_reports не были загружены
        репозиторием, возвращает False.
        """
        task_state = getattr(task, "__dict__", {})
        execution_data = task_state.get("execution_data")

        if execution_data is None:
            return False

        execution_state = getattr(execution_data, "__dict__", {})
        selected_reports = execution_state.get("selected_reports")

        return bool(selected_reports)

    @staticmethod
    def _resolve_status(*, raw_status, planned_end, today: date) -> str:
        """
        Нормализовать статус задачи с учетом даты окончания.

        Правило:
        - если задача все еще 'todo', но срок уже прошел,
          считаем ее 'not_executed'
        """
        task_status = StaffTasksService._normalize_status(raw_status)

        if task_status == "todo":
            if planned_end and planned_end < today:
                return "not_executed"

        return task_status

    @staticmethod
    def _normalize_status(raw_status) -> str:
        """
        Привести статус ORM/enum/строку к единому str-значению.
        """
        if raw_status is None:
            return ""

        if hasattr(raw_status, "value"):
            return raw_status.value

        if isinstance(raw_status, str):
            return raw_status

        return str(raw_status)

    @staticmethod
    def _status_label(task_status: str) -> str:
        """
        Подпись статуса для UI.
        """
        return {
            "todo": "Жоспарланған",
            "in_progress": "Орындалу үстінде",
            "done": "Орындалды",
            "not_executed": "Орындалмады",
            "reviewed": "Қаралды",
        }.get(task_status, "—")

    @staticmethod
    def _status_color(task_status: str) -> str:
        """
        Цветовой маркер статуса для UI.
        """
        return {
            "todo": "yellow",
            "in_progress": "green",
            "done": "blue",
            "not_executed": "red",
            "reviewed": "blue",
        }.get(task_status, "")

    @staticmethod
    def _format_period(start, end) -> str:
        """
        Отформатировать период задачи.
        """
        if start and end:
            return f"{start:%d.%m} – {end:%d.%m}"
        if start:
            return f"{start:%d.%m}"
        return "—"

    @staticmethod
    def _action_kind(task_status: str) -> str:
        """
        Тип действия для кнопки задачи.
        """
        return {
            "todo": "take",
            "not_executed": "take",
            "in_progress": "continue",
            "done": "view",
            "reviewed": "view",
        }.get(task_status, "")

    @staticmethod
    def _action_label(task_status: str) -> str:
        """
        Текст кнопки действия.
        """
        return {
            "todo": "Принять на исполнение",
            "not_executed": "Принять на исполнение",
            "in_progress": "Продолжить",
            "done": "Просмотр",
            "reviewed": "Просмотр",
        }.get(task_status, "")

    @staticmethod
    def _action_url(
            *,
            task_status: str,
            item_id: int,
            month: int,
            has_selected_reports: bool = False,
    ) -> str | None:
        """
        URL действия по задаче.
        """
        if task_status in {"todo", "not_executed"}:
            return "/staff/tasks/take"

        if task_status == "in_progress":
            return f"/staff/tasks/execute?selected_task_id={item_id}&month={month}"

        if task_status in {"done", "reviewed"}:
            if has_selected_reports:
                return f"/staff/reports/{item_id}/templates?month={month}"

            return f"/staff/reports/{item_id}/execute"

        return None

    @staticmethod
    async def take_task_to_work(
            db: AsyncSession,
            *,
            user: User,
            month_item_id: int,
    ) -> None:
        """
        Принять задачу к исполнению.

        В одной транзакции:

        - проверяется пользователь и его активные роли;
        - проверяется доступ к задаче как PRIMARY;
        - задача переводится в IN_PROGRESS;
        - уведомление ответственного переводится в ACCEPTED;
        - commit выполняется в маршруте.

        Если задача уже находится в IN_PROGRESS, метод всё равно
        синхронизирует статус уведомления.
        """

        school_id = getattr(user, "school_id", None)
        user_id = getattr(user, "id", None)

        if school_id is None or user_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Недостаточно данных пользователя "
                    "для выполнения операции."
                ),
            )

        role_ids = await SchoolStaffRepo.get_active_role_ids_by_user_id(
            db,
            user_id=cast(int, user_id),
        )

        if not role_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "У пользователя нет активной роли "
                    "сотрудника школы."
                ),
            )

        task = await StaffTasksRepo.get_task_for_staff_status_update(
            db,
            school_id=cast(int, school_id),
            staff_role_ids=role_ids,
            month_item_id=month_item_id,
        )

        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Задача не найдена или недоступна.",
            )

        staff_member_id = getattr(
            user,
            "staff_member_id",
            None,
        )

        if staff_member_id is None:
            staff_member = getattr(
                user,
                "staff_member",
                None,
            )
            staff_member_id = getattr(
                staff_member,
                "id",
                None,
            )

        if staff_member_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "У пользователя не найден "
                    "профиль сотрудника школы."
                ),
            )

        current_status = StaffTasksService._normalize_status(
            getattr(task, "status", None)
        )

        if current_status not in {
            "todo",
            "not_executed",
            "in_progress",
        }:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Эту задачу нельзя принять в исполнение "
                    "из текущего статуса."
                ),
            )

        if current_status != "in_progress":
            task.status = PlanItemStatus.IN_PROGRESS

        await MonthPlanNotificationService.accept_notification(
            db,
            month_plan_id=int(task.month_plan_id),
            school_id=cast(int, school_id),
            staff_member_id=int(staff_member_id),
            accepted_by_user_id=cast(int, user_id),
        )

        await db.flush()

    @staticmethod
    async def get_in_progress_tasks_for_execution_page(
            db: AsyncSession,
            *,
            user: User,
            month: int,
    ) -> list[MyTaskDTO]:
        """
        Получить только ответственные задачи IN_PROGRESS
        для страницы исполнения.

        Задачи, где пользователь является соисполнителем,
        в основной сценарий исполнения не включаются.
        """
        school_id = getattr(user, "school_id", None)
        user_id = getattr(user, "id", None)

        if school_id is None or user_id is None:
            return []

        role_ids = await SchoolStaffRepo.get_active_role_ids_by_user_id(
            db,
            user_id=cast(int, user_id),
        )

        if not role_ids:
            return []

        staff_role_ids = {
            int(role_id)
            for role_id in role_ids
        }

        tasks = await StaffTasksRepo.list_tasks_for_staff(
            db,
            school_id=cast(int, school_id),
            staff_role_ids=list(staff_role_ids),
            month=month,
            statuses=[PlanItemStatus.IN_PROGRESS],
        )

        today = date.today()
        result: list[MyTaskDTO] = []

        for task in tasks:
            assignment_kind = (
                StaffTasksService._resolve_staff_assignment_kind(
                    task,
                    staff_role_ids=staff_role_ids,
                )
            )

            if assignment_kind != AssignmentKind.PRIMARY:
                continue

            result.append(
                StaffTasksService._build_task_list_dto(
                    task,
                    today=today,
                    month=month,
                )
            )

        return result

    @staticmethod
    async def get_execution_page_payload(
            db: AsyncSession,
            *,
            user: User,
            month_item_id: int,
    ) -> StaffExecutionPagePayloadDTO:
        school_id = getattr(user, "school_id", None)
        user_id = getattr(user, "id", None)

        if school_id is None or user_id is None:
            return StaffExecutionPagePayloadDTO()

        role_ids = await SchoolStaffRepo.get_active_role_ids_by_user_id(
            db,
            user_id=cast(int, user_id),
        )
        if not role_ids:
            return StaffExecutionPagePayloadDTO()

        task_model = await StaffTasksRepo.get_task_for_execution(
            db,
            school_id=cast(int, school_id),
            staff_role_ids=role_ids,
            month_item_id=month_item_id,
        )
        if not task_model:
            return StaffExecutionPagePayloadDTO()

        bundle = await ReportRepo.get_execution_page_bundle(
            db,
            month_item_id=month_item_id,
        )

        selected_task = StaffTasksService._build_staff_execution_task_dto(task_model, execution_data=bundle.execution_data)
        execution = StaffTasksService._build_execution_form_dto(bundle.execution_data)
        current_draft = StaffTasksService._build_current_draft_dto(bundle.current_draft)

        control_flow = await StaffTasksService._get_control_flow_for_school(
            db,
            school_id=cast(int, school_id),
            month_item_id=month_item_id,
        )

        return StaffExecutionPagePayloadDTO(
            selected_task=selected_task,
            execution=execution,
            current_draft=current_draft,
            control_flow=control_flow,
        )

    @staticmethod
    def _build_staff_execution_task_dto(task, execution_data=None) -> StaffExecutionTaskDTO:
        """
        Собрать DTO выбранной задачи для execution-страницы.

        Источники:
        - SchoolMonthPlanItem
        - source_row11
        - review_places
        """
        raw_status = StaffTasksService._normalize_status(getattr(task, "status", None))

        period_text = StaffTasksService._format_period(
            getattr(task, "planned_start", None),
            getattr(task, "planned_end", None),
        )

        source_row11 = getattr(task, "source_row11", None)

        topic = (
                getattr(source_row11, "topic", None)
                or getattr(task, "topic", None)
                or "—"
        )
        goal = (
                getattr(source_row11, "goal", None)
                or getattr(task, "goal", None)
                or "—"
        )
        control_object = (
                getattr(source_row11, "control_object", None)
                or getattr(task, "control_object", None)
                or "—"
        )
        control_type = (
                getattr(source_row11, "control_type", None)
                or getattr(task, "control_type", None)
                or "—"
        )
        display = execution_fields(task, execution_data)

        school_id = None
        month_plan = getattr(task, "month_plan", None)
        if month_plan:
            school_plan = getattr(month_plan, "school_plan", None)
            if school_plan:
                school_id = getattr(school_plan, "school_id", None)

        return StaffExecutionTaskDTO(
            month_item_id=getattr(task, "id"),
            school_id=school_id,
            week_of_month=getattr(task, "week_of_month", None),
            planned_start=getattr(task, "planned_start", None),
            planned_end=getattr(task, "planned_end", None),
            period_text=period_text,
            topic=topic,
            goal=goal,
            control_object=control_object,
            control_type=control_type,
            **display,
            status=raw_status,
            status_label=StaffTasksService._status_label(raw_status),
            status_color=StaffTasksService._status_color(raw_status),
        )

    @staticmethod
    def _build_execution_form_dto(execution_data) -> ExecutionFormDTO:
        """
        Преобразовать ORM execution_data в ExecutionFormDTO.

        Возвращает пустой DTO, если записи еще нет.
        """
        if not execution_data:
            return ExecutionFormDTO()

        return ExecutionFormDTO.from_model(execution_data)

    @staticmethod
    def _build_current_draft_dto(current_draft_model) -> CurrentDraftDTO:
        """
        Преобразовать ORM draft-модель в легкий DTO для шаблона.
        """
        if not current_draft_model:
            return CurrentDraftDTO(
                exists=False,
                document_id=None,
            )

        return CurrentDraftDTO(
            exists=True,
            document_id=getattr(current_draft_model, "id", None),
        )

    @staticmethod
    async def _get_control_flow_for_school(db: AsyncSession, *, school_id: int, month_item_id: int):
        catalog = await ExecutionRepo.get_algorithm_catalog(db, month_item_id=month_item_id, school_id=school_id)
        subjects = [dict(code=str(row['id']), label=row['name_ru'] or row['name_kz'], label_kk=row['name_kz'] or row['name_ru']) for row in catalog['subjects']]
        teachers = {}
        by_subject = {}
        primary = {}
        grades = {row['id']: row['grade_level'] for row in catalog['classes']}
        for row in catalog['teaching']:
            teacher = dict(code=str(row['teacher_id']), label=row['full_name'])
            teachers[teacher['code']] = teacher
            by_subject.setdefault(str(row['subject_id']), {})[teacher['code']] = teacher
            if grades.get(row['class_id'], 99) <= 4:
                primary[teacher['code']] = teacher
        result = build_control_flow_for_ui(subjects=subjects, all_teachers=list(teachers.values()),
                                           teachers_by_subject={key: list(values.values()) for key, values in by_subject.items()},
                                           primary_teachers=list(primary.values()))
        result['report_labels'] = await ReportTypeRepo.get_labels(db)
        result['algorithm_catalog'] = catalog
        return result
