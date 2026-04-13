from typing import cast, Any
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.modules.planning.control_flow import CONTROL_CONFIG
from app.modules.planning.enums import PlanItemStatus, ControlScope, ControlForm, ControlKind
from app.modules.reports.enums import ReportType
from app.modules.planning.models_month_plan import SchoolMonthPlanItem
from app.modules.staff.schemas import MyTaskDTO, StaffExecutionTaskDTO
from app.modules.staff.staff_repo import SchoolStaffRepo
from app.modules.staff.task_repo import StaffTasksRepo, SchoolMonthPlanItemExecutionRepo
from app.modules.users.models import User


class StaffTasksService:
    """
    Сервис работы с задачами сотрудников (ВШК):
    - получение списка задач пользователя
    - взятие задачи в работу
    - получение списка принятых задач для страницы исполнения
    - получение одной задачи для исполнения
    - сохранение результатов исполнения
    """

    # ---------------------------
    # 🔹 Общие helper-методы
    # ---------------------------
    @staticmethod
    def _status_value(value: Any) -> str:
        return value.value if hasattr(value, "value") else str(value)

    @staticmethod
    def _extract_status_info(raw_status: Any) -> tuple[str, str]:
        if isinstance(raw_status, PlanItemStatus):
            return raw_status.value, raw_status.label_kz

        if raw_status is not None:
            status_value = str(raw_status)
            try:
                return status_value, PlanItemStatus(status_value).label_kz
            except ValueError:
                return status_value, status_value

        return "", ""

    @staticmethod
    def _build_review_place_text(item: SchoolMonthPlanItem) -> str:
        review_place_text = "—"

        if getattr(item, "review_places", None):
            parts: list[str] = []

            for rp in item.review_places:
                review_place = getattr(rp, "review_place", None)
                if not review_place:
                    continue

                parts.append(
                    getattr(review_place, "label_kz", None) or str(review_place)
                )

            if parts:
                review_place_text = ", ".join(parts)

        return review_place_text

    @staticmethod
    def _to_my_task_dto(item: SchoolMonthPlanItem) -> MyTaskDTO:
        src = item.source_row11
        review_place_text = StaffTasksService._build_review_place_text(item)
        status_value, status_label = StaffTasksService._extract_status_info(
            getattr(item, "status", None)
        )

        print(
            "DTO BUILD:",
            "id=", item.id,
            "raw_status=", getattr(item, "status", None),
        )

        return MyTaskDTO(
            month_item_id=item.id,
            week_of_month=item.week_of_month,
            planned_start=item.planned_start,
            planned_end=item.planned_end,
            topic=getattr(src, "topic", None),
            goal=getattr(src, "goal", None),
            control_object=getattr(src, "control_object", None),
            control_type=getattr(src, "control_type", None),
            review_place=review_place_text,
            status=status_value,
            status_label=status_label,
        )

    @staticmethod
    def _to_execution_task_dto(item: SchoolMonthPlanItem) -> StaffExecutionTaskDTO:
        src = item.source_row11
        review_place_text = StaffTasksService._build_review_place_text(item)
        status_value, status_label = StaffTasksService._extract_status_info(
            getattr(item, "status", None)
        )

        print(
            "DTO STATUS:",
            "id=", item.id,
            "status_value=", status_value,
            "status_label=", status_label,
        )

        return StaffExecutionTaskDTO(
            month_item_id=item.id,
            week_of_month=item.week_of_month,
            planned_start=item.planned_start,
            planned_end=item.planned_end,
            topic=getattr(src, "topic", None),
            goal=getattr(src, "goal", None),
            control_object=getattr(src, "control_object", None),
            control_type=getattr(src, "control_type", None),
            control_form=getattr(src, "control_form", None),
            review_place=review_place_text,
            status=status_value,
            status_label=status_label,
        )

    # ---------------------------
    # 🔹 Получение контекста пользователя
    # ---------------------------
    @staticmethod
    async def _get_user_context(
            db: AsyncSession,
            *,
            user: User,
    ) -> tuple[int, int, list[int]]:
        """
        Возвращает:
        - school_id
        - user_id
        - список активных role_id сотрудника
        """
        school_id_raw = getattr(user, "school_id", None)
        user_id_raw = getattr(user, "id", None)

        if school_id_raw is None or user_id_raw is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Нет доступа",
            )

        school_id = cast(int, school_id_raw)
        user_id = cast(int, user_id_raw)

        staff_member = await SchoolStaffRepo.get_member_by_user_id(
            db,
            user_id=user_id,
        )
        if not staff_member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Сотрудник не найден",
            )

        staff_role_ids = [
            cast(int, role.id)
            for role in (staff_member.roles or [])
            if role.is_active
        ]
        if not staff_role_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="У пользователя нет активных ролей исполнителя",
            )

        return school_id, user_id, staff_role_ids

    # ---------------------------
    # 🔹 Получение задачи с проверкой доступа
    # ---------------------------
    @staticmethod
    async def _get_accessible_item(
            db: AsyncSession,
            *,
            user: User,
            month_item_id: int,
    ) -> tuple[SchoolMonthPlanItem, int]:
        school_id, user_id, staff_role_ids = await StaffTasksService._get_user_context(
            db,
            user=user,
        )

        item = await StaffTasksRepo.get_staff_task_by_id(
            db,
            month_item_id=month_item_id,
            school_id=school_id,
            staff_role_ids=staff_role_ids,
        )
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Задача не найдена или недоступна",
            )

        return item, user_id

    # ---------------------------
    # 🔹 Мои задачи (общий список)
    # ---------------------------
    @staticmethod
    async def get_my_tasks_page(
            db: AsyncSession,
            *,
            user: User,
            month: int,
    ) -> list[MyTaskDTO]:
        school_id_raw = getattr(user, "school_id", None)
        if school_id_raw is None:
            return []

        school_id = cast(int, school_id_raw)

        user_id_raw = getattr(user, "id", None)
        if user_id_raw is None:
            return []

        staff_member = await SchoolStaffRepo.get_member_by_user_id(
            db,
            user_id=cast(int, user_id_raw),
        )
        if not staff_member:
            return []

        staff_role_ids = [
            cast(int, role.id)
            for role in (staff_member.roles or [])
            if role.is_active
        ]
        if not staff_role_ids:
            return []

        items = await StaffTasksRepo.list_tasks_for_staff(
            db,
            school_id=school_id,
            staff_role_ids=staff_role_ids,
            month=month,
        )

        for item in items:
            print(
                "LIST BEFORE RUNTIME:",
                "id=", item.id,
                "status=", item.status,
                "planned_end=", item.planned_end,
            )

        changed = await SchoolMonthPlanItemStatusService.apply_runtime_overdue_rule(
            db,
            tasks=items,
        )
        print("RUNTIME CHANGED COUNT =", changed)

        for item in items:
            print(
                "LIST AFTER RUNTIME:",
                "id=", item.id,
                "status=", item.status,
                "planned_end=", item.planned_end,
            )

        return [StaffTasksService._to_my_task_dto(item) for item in items]

    # ---------------------------
    # 🔹 Список принятых задач для страницы исполнения
    # ---------------------------
    @staticmethod
    async def get_in_progress_tasks_for_execution_page(
            db: AsyncSession,
            *,
            user: User,
            month: int,
    ) -> list[StaffExecutionTaskDTO]:
        """
        Возвращает список задач исполнителя,
        которые уже приняты в работу (IN_PROGRESS),
        для страницы выполнения задач.
        """
        school_id, _user_id, staff_role_ids = await StaffTasksService._get_user_context(
            db,
            user=user,
        )

        items = await StaffTasksRepo.list_tasks_for_staff(
            db,
            school_id=school_id,
            staff_role_ids=staff_role_ids,
            month=month,
            statuses=[PlanItemStatus.IN_PROGRESS],
        )

        return [StaffTasksService._to_execution_task_dto(item) for item in items]

    # ---------------------------
    # 🔹 Взять задачу в работу
    # ---------------------------
    @staticmethod
    async def take_task_to_work(
            db: AsyncSession,
            *,
            user: User,
            month_item_id: int,
    ) -> None:
        item, _ = await StaffTasksService._get_accessible_item(
            db,
            user=user,
            month_item_id=month_item_id,
        )

        current_status = getattr(item.status, "value", item.status)

        if current_status == PlanItemStatus.DONE.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Выполненную задачу нельзя принять в работу",
            )

        print("TAKE BEFORE:", item.id, item.status)

        item.status = PlanItemStatus.IN_PROGRESS

        print("TAKE AFTER SET:", item.id, item.status)

        await db.commit()
        await db.refresh(item)

        print("TAKE AFTER COMMIT:", item.id, item.status)

    # ---------------------------
    # 🔹 Валидация выбора параметров исполнения
    # ---------------------------
    @staticmethod
    def _validate_execution_choice(
            *,
            control_scope: str,
            control_form: str,
            control_kind: str,
            report_types: list[str],
    ) -> None:
        try:
            scope_enum = ControlScope(control_scope)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Некорректный объект контроля",
            )

        try:
            form_enum = ControlForm(control_form)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Некорректная форма контроля",
            )

        try:
            kind_enum = ControlKind(control_kind)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Некорректный вид контроля",
            )

        try:
            report_enum = ReportType(report_types)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Некорректный тип отчета",
            )

        scope_config = CONTROL_CONFIG.get(scope_enum)
        if not scope_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Для выбранного объекта контроля нет конфигурации",
            )

        form_config = scope_config.get(form_enum)
        if not form_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Выбранная форма не подходит для этого объекта контроля",
            )

        allowed_kinds = form_config.get("kinds", [])
        if kind_enum not in allowed_kinds:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Выбранный вид контроля не подходит для этой формы",
            )

        allowed_reports = form_config.get("reports", [])
        if report_enum not in allowed_reports:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Выбранный тип отчета не подходит для указанной комбинации",
            )

    @staticmethod
    def _validate_action(action: str) -> None:
        allowed_actions = {"save", "done", "not_executed"}
        if action not in allowed_actions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Некорректное действие",
            )

    # ---------------------------
    # 🔹 Получить задачу для исполнения
    # ---------------------------
    @staticmethod
    async def get_task_for_execution(
            db: AsyncSession,
            *,
            user: User,
            month_item_id: int,
    ) -> SchoolMonthPlanItem:
        """
        Возвращает задачу и автоматически переводит в IN_PROGRESS,
        если она была в TODO.
        """
        item, _user_id = await StaffTasksService._get_accessible_item(
            db,
            user=user,
            month_item_id=month_item_id,
        )

        current_status = StaffTasksService._status_value(item.status)

        if current_status == PlanItemStatus.TODO.value:
            item.status = PlanItemStatus.IN_PROGRESS
            await db.commit()
            await db.refresh(item)

        return item

    # ---------------------------
    # 🔹 Сохранение исполнения задачи
    # ---------------------------
    @staticmethod
    async def save_task_execution(
            db: AsyncSession,
            *,
            user: User,
            month_item_id: int,
            action: str,
            executed_at: date | None = None,
            control_scope: str,
            control_form: str,
            control_kind: str,
            report_types: list[str],
            evidence_note: str | None = None,
            reference_text: str | None = None,
            conclusion: str | None = None,
            recommendations: str | None = None,
            review_result: str | None = None,
            planned_review_place: str | None = None,
    ) -> None:
        """
        Сохраняет выполнение задачи.

        action:
        - save → сохранить черновик
        - done → выполнено
        - not_executed → не выполнено
        """
        StaffTasksService._validate_action(action)
        StaffTasksService._validate_execution_choice(
            control_scope=control_scope,
            control_form=control_form,
            control_kind=control_kind,
            report_types=report_types,
        )

        item, user_id = await StaffTasksService._get_accessible_item(
            db,
            user=user,
            month_item_id=month_item_id,
        )

        current_status = StaffTasksService._status_value(item.status)

        if current_status in {
            PlanItemStatus.DONE.value,
            PlanItemStatus.NOT_EXECUTED.value,
        } and action == "save":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя сохранять черновик для завершенной задачи",
            )

        execution = await SchoolMonthPlanItemExecutionRepo.get_or_create(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
        )

        await SchoolMonthPlanItemExecutionRepo.update(
            db,
            obj=execution,
            data={
                "control_scope": control_scope,
                "control_form": control_form,
                "control_kind": control_kind,
                "report_types": report_types,
                "evidence_note": evidence_note,
                "reference_text": reference_text,
                "conclusion": conclusion,
                "recommendations": recommendations,
                "review_result": review_result,
                "planned_review_place": planned_review_place,
            },
            user_id=user_id,
        )

        if action == "done":
            fact_date = executed_at or date.today()

            item.status = PlanItemStatus.DONE
            item.executed_at = fact_date
            item.completed_at = datetime.now(timezone.utc)
            item.completed_by_user_id = user.id

        elif action == "not_executed":
            if current_status == PlanItemStatus.DONE.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Нельзя перевести выполненную задачу в статус 'Не выполнено'",
                )

            item.status = PlanItemStatus.NOT_EXECUTED
            item.executed_at = None
            item.completed_at = None
            item.completed_by_user_id = None

        elif action == "save":
            if current_status == PlanItemStatus.TODO.value:
                item.status = PlanItemStatus.IN_PROGRESS

        await db.commit()


class SchoolMonthPlanItemStatusService:
    @classmethod
    async def mark_in_progress(
            cls,
            db: AsyncSession,
            *,
            task: SchoolMonthPlanItem,
    ) -> SchoolMonthPlanItem:
        """
        Переводит задачу в IN_PROGRESS, если это допустимо.
        DONE и NOT_EXECUTED не трогаем автоматически.
        """
        if task.status in (PlanItemStatus.DONE, PlanItemStatus.NOT_EXECUTED):
            return task

        task.status = PlanItemStatus.IN_PROGRESS
        await db.flush()
        return task

    @classmethod
    async def mark_done(
            cls,
            db: AsyncSession,
            *,
            task: SchoolMonthPlanItem,
            user: User,
            executed_at: date | None = None,
    ) -> SchoolMonthPlanItem:
        """
        Завершает задачу.
        executed_at — фактическая дата исполнения.
        completed_at — дата/время закрытия задачи в системе.
        completed_by_user_id — кто закрыл задачу.
        """
        fact_date = executed_at or date.today()

        task.status = PlanItemStatus.DONE
        task.executed_at = fact_date
        task.completed_at = datetime.now(timezone.utc)
        task.completed_by_user_id = user.id

        await db.flush()
        return task

    @classmethod
    async def mark_not_executed(
            cls,
            db: AsyncSession,
            *,
            task: SchoolMonthPlanItem,
    ) -> SchoolMonthPlanItem:
        """
        Ручной перевод в NOT_EXECUTED.
        Если задача уже DONE, не трогаем.
        """
        if task.status == PlanItemStatus.DONE:
            return task

        task.status = PlanItemStatus.NOT_EXECUTED
        task.executed_at = None
        task.completed_at = None
        task.completed_by_user_id = None

        await db.flush()
        return task

    @classmethod
    async def auto_mark_expired_as_not_executed(
            cls,
            db: AsyncSession,
    ) -> int:
        """
        Массово переводит в NOT_EXECUTED только просроченные TODO-задачи.
        IN_PROGRESS не трогаем.
        """
        today = date.today()

        stmt = (
            update(SchoolMonthPlanItem)
            .where(
                SchoolMonthPlanItem.status == PlanItemStatus.TODO,
                SchoolMonthPlanItem.planned_end.is_not(None),
                SchoolMonthPlanItem.planned_end < today,
            )
            .values(
                status=PlanItemStatus.NOT_EXECUTED,
                executed_at=None,
                completed_at=None,
                completed_by_user_id=None,
            )
            .execution_options(synchronize_session=False)
        )

        result = await db.execute(stmt)
        await db.commit()

        return result.rowcount or 0

    # ---------------------------
    # 🔹Runtime-проверка при открытии списка задач
    # ---------------------------
    @classmethod
    async def apply_runtime_overdue_rule(
            cls,
            db: AsyncSession,
            *,
            tasks: list[SchoolMonthPlanItem],
    ) -> int:
        """
        При открытии страниц автоматически переводит в NOT_EXECUTED
        только просроченные задачи со статусом TODO.

        Важно:
        - IN_PROGRESS не трогаем
        - DONE не трогаем
        - NOT_EXECUTED не трогаем
        """
        today = date.today()
        changed_count = 0

        for task in tasks:
            print(
                "RUNTIME CHECK:",
                "id=", task.id,
                "raw_status=", task.status,
                "status_type=", type(task.status),
                "planned_end=", task.planned_end,
                "today=", today,
            )

            if (
                    task.status == PlanItemStatus.TODO
                    and task.planned_end is not None
                    and task.planned_end < today
            ):
                print("RUNTIME CHANGE TO NOT_EXECUTED:", task.id)

                task.status = PlanItemStatus.NOT_EXECUTED
                task.executed_at = None
                task.completed_at = None
                task.completed_by_user_id = None
                changed_count += 1

        if changed_count:
            await db.commit()

        return changed_count

    @classmethod
    def is_completed_on_time(cls, task: SchoolMonthPlanItem) -> bool:
        """
        Выполнено вовремя:
        - статус DONE
        - есть фактическая дата исполнения
        - есть плановый срок
        - executed_at <= planned_end
        """
        return (
                task.status == PlanItemStatus.DONE
                and task.executed_at is not None
                and task.planned_end is not None
                and task.executed_at <= task.planned_end
        )

    @classmethod
    def is_completed_late(cls, task: SchoolMonthPlanItem) -> bool:
        """
        Выполнено поздно:
        - статус DONE
        - есть фактическая дата исполнения
        - есть плановый срок
        - executed_at > planned_end
        """
        return (
                task.status == PlanItemStatus.DONE
                and task.executed_at is not None
                and task.planned_end is not None
                and task.executed_at > task.planned_end
        )

    @classmethod
    def is_not_executed(cls, task: SchoolMonthPlanItem) -> bool:
        return task.status == PlanItemStatus.NOT_EXECUTED

    @classmethod
    def get_result_code(cls, task: SchoolMonthPlanItem) -> str | None:
        """
        Удобный код для статистики и шаблонов:
        - on_time
        - late
        - not_executed
        - None
        """
        if cls.is_not_executed(task):
            return "not_executed"

        if cls.is_completed_on_time(task):
            return "on_time"

        if cls.is_completed_late(task):
            return "late"

        return None

    @classmethod
    def get_result_label(cls, task: SchoolMonthPlanItem) -> str:
        """
        Человекочитаемый текст для шаблонов и отчетов.
        """
        if cls.is_not_executed(task):
            return "Не выполнено"

        if cls.is_completed_on_time(task):
            return "Выполнено вовремя"

        if cls.is_completed_late(task):
            return "Выполнено поздно"

        if task.status == PlanItemStatus.IN_PROGRESS:
            return "Выполняется"

        if task.status == PlanItemStatus.TODO:
            return "Запланировано"

        if task.status == PlanItemStatus.DONE:
            return "Выполнено"

        return "—"

