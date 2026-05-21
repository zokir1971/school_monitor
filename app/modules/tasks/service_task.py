from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import cast

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import PlanItemStatus
from app.modules.reports.control_flow import build_control_flow_for_ui
from app.modules.reports.report_repo import ReportRepo
from app.modules.reports.report_schemas import (
    CurrentDraftDTO,
    ExecutionFormDTO,
    StaffExecutionPagePayloadDTO,
    StaffExecutionTaskDTO,
)
from app.modules.staff.staff_repo import SchoolStaffRepo
from app.modules.tasks.schemas import MyTaskDTO, MyTaskRow
from app.modules.tasks.task_repo import StaffTasksRepo
from app.modules.users.models import User


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
    ) -> list[MyTaskDTO]:
        """
        Получить список задач сотрудника за месяц.

        Что делает:
        - определяет school_id и user_id
        - получает активные staff_role пользователя
        - запрашивает строки задач через StaffTasksRepo
        - преобразует строки в MyTaskDTO

        Почему метод на service-уровне:
        - здесь собирается пользовательский сценарий,
          а не просто один SQL-запрос
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

        rows = await StaffTasksRepo.list_tasks_for_staff(
            db,
            school_id=cast(int, school_id),
            staff_role_ids=role_ids,
            month=month,
        )

        today = date.today()

        return [
            StaffTasksService._build_task_dto(row, today=today, month=month)
            for row in rows
        ]

    @staticmethod
    def _build_task_dto(row: MyTaskRow, *, today: date, month: int) -> MyTaskDTO:
        """
        Преобразовать строку списка задач в DTO для страницы 'Мои задачи'.
        """
        task_status = StaffTasksService._resolve_status(
            raw_status=row.status,
            planned_end=row.planned_end,
            today=today,
        )

        return MyTaskDTO(
            month_item_id=row.month_item_id,
            week_of_month=row.week_of_month,
            planned_start=row.planned_start,
            planned_end=row.planned_end,
            period_text=StaffTasksService._format_period(
                row.planned_start,
                row.planned_end,
            ),
            topic=row.topic or "—",
            goal=row.goal or "—",
            control_object=row.control_object or "—",
            control_type=row.control_type or "—",
            review_place=row.review_place or "—",
            status=task_status,
            status_label=StaffTasksService._status_label(task_status),
            status_color=StaffTasksService._status_color(task_status),
            action_kind=StaffTasksService._action_kind(task_status),
            action_url=StaffTasksService._action_url(
                task_status=task_status,
                item_id=row.month_item_id,
                month=month,
                has_selected_reports=row.has_selected_reports,
            ),
            action_label=StaffTasksService._action_label(task_status),
        )

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

        if task_status == "done":
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
        Перевести задачу в статус IN_PROGRESS.

        Делает:
        - проверку school_id/user_id
        - проверку активных staff roles
        - проверку доступа к задаче
        - проверку допустимости перехода статуса
        - commit изменения
        """
        school_id = getattr(user, "school_id", None)
        user_id = getattr(user, "id", None)

        if school_id is None or user_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно данных пользователя для выполнения операции.",
            )

        role_ids = await SchoolStaffRepo.get_active_role_ids_by_user_id(
            db,
            user_id=cast(int, user_id),
        )
        if not role_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="У пользователя нет активной роли сотрудника школы.",
            )

        task = await StaffTasksRepo.get_task_for_staff_status_update(
            db,
            school_id=cast(int, school_id),
            staff_role_ids=role_ids,
            month_item_id=month_item_id,
        )
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Задача не найдена или недоступна.",
            )

        current_status = StaffTasksService._normalize_status(getattr(task, "status", None))

        if current_status == "in_progress":
            return

        if current_status not in {"todo", "not_executed"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Эту задачу нельзя принять в исполнение из текущего статуса.",
            )

        task.status = PlanItemStatus.IN_PROGRESS
        await db.commit()

    @staticmethod
    async def get_in_progress_tasks_for_execution_page(
            db: AsyncSession,
            *,
            user: User,
            month: int,
    ) -> list[MyTaskDTO]:
        """
        Получить легкий список задач IN_PROGRESS
        для верхнего селектора страницы исполнения.
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

        rows = await StaffTasksRepo.list_tasks_for_staff(
            db,
            school_id=cast(int, school_id),
            staff_role_ids=role_ids,
            month=month,
            statuses=[PlanItemStatus.IN_PROGRESS],
        )

        today = date.today()

        return [
            StaffTasksService._build_task_dto(row, today=today, month=month)
            for row in rows
            if StaffTasksService._resolve_status(
                raw_status=row.status,
                planned_end=row.planned_end,
                today=today,
            ) == "in_progress"
        ]

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

        selected_task = StaffTasksService._build_staff_execution_task_dto(task_model)
        execution = StaffTasksService._build_execution_form_dto(bundle.execution_data)
        current_draft = StaffTasksService._build_current_draft_dto(bundle.current_draft)

        control_flow = await StaffTasksService._get_control_flow_for_school(
            db,
            school_id=cast(int, school_id),
        )

        return StaffExecutionPagePayloadDTO(
            selected_task=selected_task,
            execution=execution,
            current_draft=current_draft,
            control_flow=control_flow,
        )

    @staticmethod
    def _build_staff_execution_task_dto(task) -> StaffExecutionTaskDTO:
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
        control_form = (
                getattr(source_row11, "control_form", None)
                or getattr(task, "control_form", None)
                or "—"
        )

        review_place = "—"
        review_places = getattr(task, "review_places", None)
        if review_places:
            labels: list[str] = []
            for rp in review_places:
                place = getattr(rp, "review_place", None)
                if not place:
                    continue
                label = (
                        getattr(place, "label_kz", None)
                        or getattr(place, "label_ru", None)
                        or str(place)
                )
                if label:
                    labels.append(label)
            if labels:
                review_place = ", ".join(labels)

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
            control_form=control_form,
            review_place=review_place,
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
    async def _get_control_flow_for_school(
            db: AsyncSession,
            *,
            school_id: int | None,
    ) -> dict[str, object] | None:
        """
        Построить полный control_flow для task_execute.js на основе сотрудников школы.

        Что делает:
        - получает staff members школы
        - собирает динамические данные:
            - subjects
            - all_teachers
            - teachers_by_subject
            - primary_teachers
        - передает их в build_control_flow_for_ui(), где уже хранятся:
            - scopes
            - kinds
            - forms_by_scope
            - reports_by_scope
            - details_by_scope

        Почему так:
        - service не дублирует бизнес-правила control-flow
        - единый источник конфигурации остается в reports.control_config
        """
        if not school_id:
            return None

        staff_members = await SchoolStaffRepo.get_school_staff_members(
            db,
            school_id=school_id,
        )

        subjects_set: set[str] = set()
        teachers_by_subject_map: dict[str, list[dict[str, str]]] = defaultdict(list)
        primary_teachers_map: dict[str, dict[str, str]] = {}
        all_teachers_map: dict[str, dict[str, str]] = {}

        primary_subject_names = {
            "бастауыш оқуы",
            "начальные классы",
            "начальное обучение",
            "бастауыш сынып",
        }

        for item in staff_members:
            full_name = (getattr(item, "full_name", None) or "").strip()
            subject_raw = (getattr(item, "subject", None) or "").strip()

            if not full_name:
                continue

            teacher_item = {
                "code": str(getattr(item, "id")),
                "label": full_name,
            }

            all_teachers_map[teacher_item["code"]] = teacher_item

            if not subject_raw:
                continue

            normalized_raw = subject_raw.replace(";", ",").replace("/", ",")
            subject_list = [s.strip() for s in normalized_raw.split(",") if s.strip()]

            for subject_name in subject_list:
                subjects_set.add(subject_name)
                teachers_by_subject_map[subject_name].append(teacher_item)

                if subject_name.lower() in primary_subject_names:
                    primary_teachers_map[teacher_item["code"]] = teacher_item

        subjects = [
            {"code": subject_name, "label": subject_name}
            for subject_name in sorted(subjects_set)
        ]

        return build_control_flow_for_ui(
            subjects=subjects,
            all_teachers=list(all_teachers_map.values()),
            teachers_by_subject=dict(teachers_by_subject_map),
            primary_teachers=list(primary_teachers_map.values()),
        )
