# app/modules/reports/services/report_assignment_service.py

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import PlanItemStatus
from app.modules.reports.enums import ReportAssignmentStatus
from app.modules.reports.repositories.report_assignment_repo import (
    ReportAssignmentRepo,
)
from app.modules.reports.schemas.report_assignment_dto import (
    ReportAssignmentInputDTO,
    ReportAssignmentPageDTO,
    ReportAssignmentSaveResultDTO,
)
from app.modules.staff.staff_repo import SchoolStaffRepo
from app.modules.tasks.task_repo import StaffTasksRepo
from app.modules.users.models import User


class ReportAssignmentService:
    """
    Сервис распределения выбранных системных отчётов
    между ответственным исполнителем и соисполнителями.

    Сервис отвечает за бизнес-правила:

    - доступ имеет только ответственный PRIMARY;
    - задача должна принадлежать школе пользователя;
    - задача должна быть принята в исполнение;
    - отчёт должен относиться к этой задаче;
    - сотрудник должен быть назначен на эту задачу;
    - один выбранный отчёт получает одного исполнителя;
    - все выбранные отчёты должны быть распределены.

    Репозиторий выполняет SQL-запросы и изменяет ORM-модели.

    Commit внутри сервиса не выполняется.
    Границей транзакции управляет web-маршрут.
    """

    # =========================================================
    # PAGE
    # =========================================================

    @classmethod
    async def get_assignment_page(
        cls,
        db: AsyncSession,
        *,
        user: User,
        month_item_id: int,
        month: int,
    ) -> ReportAssignmentPageDTO:
        """
        Получить данные страницы распределения отчётов.

        Страница доступна только ответственному исполнителю
        PRIMARY указанной задачи.
        """

        school_id, user_id = cls._require_user_context(user)

        role_ids = await cls._get_active_role_ids(
            db,
            user_id=user_id,
        )

        await cls._require_primary_executor(
            db,
            month_item_id=month_item_id,
            school_id=school_id,
            staff_role_ids=role_ids,
        )

        task = await cls._get_accessible_task(
            db,
            school_id=school_id,
            staff_role_ids=role_ids,
            month_item_id=month_item_id,
        )

        cls._require_task_in_progress(task)

        executors = await ReportAssignmentRepo.list_executor_choices(
            db,
            month_item_id=month_item_id,
            school_id=school_id,
        )

        reports = await ReportAssignmentRepo.list_report_rows(
            db,
            month_item_id=month_item_id,
        )

        source_row11 = getattr(
            task,
            "source_row11",
            None,
        )

        planned_start = getattr(
            task,
            "planned_start",
            None,
        )

        planned_end = getattr(
            task,
            "planned_end",
            None,
        )

        return ReportAssignmentPageDTO(
            month_item_id=month_item_id,
            month=month,
            task_topic=(
                getattr(source_row11, "topic", None)
                or getattr(task, "topic", None)
                or "—"
            ),
            task_goal=(
                getattr(source_row11, "goal", None)
                or getattr(task, "goal", None)
                or "—"
            ),
            period_text=cls._format_period(
                planned_start,
                planned_end,
            ),
            executors=executors,
            reports=reports,
        )

    # =========================================================
    # SAVE
    # =========================================================

    @classmethod
    async def save_assignments(
        cls,
        db: AsyncSession,
        *,
        user: User,
        month_item_id: int,
        assignments: Sequence[ReportAssignmentInputDTO],
    ) -> ReportAssignmentSaveResultDTO:
        """
        Сохранить полное распределение выбранных отчётов.

        Форма должна передать по одному назначению
        для каждого выбранного отчёта задачи.

        Сценарий:

        1. Проверить пользователя и активные роли.
        2. Проверить, что пользователь является PRIMARY.
        3. Проверить статус задачи.
        4. Проверить отсутствие дублей в форме.
        5. Проверить принадлежность отчётов задаче.
        6. Проверить принадлежность сотрудников задаче.
        7. Заблокировать существующие назначения.
        8. Создать, обновить или оставить назначения без изменений.
        9. Выполнить flush.

        Commit выполняется маршрутом.
        """

        school_id, user_id = cls._require_user_context(user)

        role_ids = await cls._get_active_role_ids(
            db,
            user_id=user_id,
        )

        await cls._require_primary_executor(
            db,
            month_item_id=month_item_id,
            school_id=school_id,
            staff_role_ids=role_ids,
        )

        task = await cls._get_accessible_task(
            db,
            school_id=school_id,
            staff_role_ids=role_ids,
            month_item_id=month_item_id,
        )

        cls._require_task_in_progress(task)
        await ReportAssignmentRepo.lock_report_selection(db, month_item_id=month_item_id)

        normalized_assignments = (
            cls._normalize_assignment_inputs(
                assignments
            )
        )

        assignable_report_rows = (
            await ReportAssignmentRepo.list_report_rows(
                db,
                month_item_id=month_item_id,
            )
        )

        selected_report_ids = {
            int(report.selected_report_id)
            for report in assignable_report_rows
            if report.assignable
        }

        if not selected_report_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Для задачи не выбраны системные отчёты. "
                    "Сначала сформируйте алгоритм выполнения."
                ),
            )

        cls._validate_complete_report_set(
            submitted_report_ids=set(
                normalized_assignments
            ),
            expected_report_ids=selected_report_ids,
        )

        allowed_staff_member_ids = (
            await ReportAssignmentRepo
            .get_allowed_staff_member_ids(
                db,
                month_item_id=month_item_id,
                school_id=school_id,
            )
        )

        cls._validate_assigned_staff(
            assignments=normalized_assignments,
            allowed_staff_member_ids=(
                allowed_staff_member_ids
            ),
        )

        existing_assignments = await (
            ReportAssignmentRepo
            .list_assignments_for_update(
                db,
                selected_report_ids=sorted(
                    selected_report_ids
                ),
            )
        )

        existing_by_report_id = {
            int(assignment.selected_report_id): assignment
            for assignment in existing_assignments
        }

        for selected_report_id, staff_member_id in normalized_assignments.items():
            current = existing_by_report_id.get(selected_report_id)
            if (current is not None
                    and cls._normalize_status(current.status) == ReportAssignmentStatus.COMPLETED.value
                    and int(current.staff_member_id) != staff_member_id):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail="Выполненный отчёт нельзя переназначить. / Аяқталған есепті қайта тағайындауға болмайды.")

        created_count = 0
        updated_count = 0
        unchanged_count = 0

        for (
            selected_report_id,
            staff_member_id,
        ) in normalized_assignments.items():

            existing = existing_by_report_id.get(
                selected_report_id
            )

            if existing is None:
                await ReportAssignmentRepo.create(
                    db,
                    selected_report_id=(
                        selected_report_id
                    ),
                    staff_member_id=staff_member_id,
                    assigned_by_user_id=user_id,
                    flush=False,
                )

                created_count += 1
                continue

            if (
                int(existing.staff_member_id)
                == staff_member_id
            ):
                unchanged_count += 1
                continue

            await ReportAssignmentRepo.update_executor(
                db,
                assignment=existing,
                staff_member_id=staff_member_id,
                assigned_by_user_id=user_id,
                    flush=False,
            )

            updated_count += 1

        await db.flush()

        return ReportAssignmentSaveResultDTO(
            month_item_id=month_item_id,
            created_count=created_count,
            updated_count=updated_count,
            unchanged_count=unchanged_count,
            deleted_count=0,
        )

    # =========================================================
    # REASSIGN / WAIVE
    # =========================================================

    @classmethod
    async def reassign_report(
        cls,
        db: AsyncSession,
        *,
        user: User,
        month_item_id: int,
        selected_report_id: int,
        staff_member_id: int,
    ):
        """
        Переназначить один выбранный системный отчёт.

        Разрешено только ответственному PRIMARY текущей задачи.

        Новый исполнитель должен быть назначен на задачу как
        PRIMARY или CO_EXECUTOR.

        При переназначении repository переводит назначение
        в PENDING и очищает WAIVED-поля.

        Commit выполняется маршрутом.
        """

        school_id, user_id, _, task = (
            await cls._prepare_primary_action(
                db,
                user=user,
                month_item_id=month_item_id,
            )
        )

        cls._require_task_in_progress(task)
        await ReportAssignmentRepo.lock_report_selection(db, month_item_id=month_item_id)

        selected_report_id = cls._require_positive_id(
            selected_report_id,
            field_name="выбранного отчёта",
        )

        staff_member_id = cls._require_positive_id(
            staff_member_id,
            field_name="исполнителя отчёта",
        )

        await cls._require_report_belongs_to_task(
            db,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
        )

        await cls._require_allowed_staff_member(
            db,
            month_item_id=month_item_id,
            school_id=school_id,
            staff_member_id=staff_member_id,
        )

        assignment = (
            await ReportAssignmentRepo.get_assignment_for_update(
                db,
                selected_report_id=selected_report_id,
            )
        )

        if assignment is None:
            return await ReportAssignmentRepo.create(
                db,
                selected_report_id=selected_report_id,
                staff_member_id=staff_member_id,
                assigned_by_user_id=user_id,
            )

        current_status = cls._normalize_status(
            getattr(assignment, "status", None)
        )

        if current_status == ReportAssignmentStatus.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Выполненный отчёт нельзя переназначить.",
            )

        if (
            int(assignment.staff_member_id) == staff_member_id
            and current_status == ReportAssignmentStatus.PENDING.value
        ):
            return assignment

        return await ReportAssignmentRepo.update_executor(
            db,
            assignment=assignment,
            staff_member_id=staff_member_id,
            assigned_by_user_id=user_id,
        )

    @classmethod
    async def waive_report(
        cls,
        db: AsyncSession,
        *,
        user: User,
        month_item_id: int,
        selected_report_id: int,
        reason: str,
    ):
        """
        Освободить один назначенный системный отчёт
        от обязательного выполнения.

        Разрешено только ответственному PRIMARY.

        Причина обязательна и сохраняется для аудита.

        COMPLETED-отчёт освобождать нельзя.

        Commit выполняется маршрутом.
        """

        _, user_id, _, task = await cls._prepare_primary_action(
            db,
            user=user,
            month_item_id=month_item_id,
        )

        cls._require_task_in_progress(task)

        selected_report_id = cls._require_positive_id(
            selected_report_id,
            field_name="выбранного отчёта",
        )

        normalized_reason = cls._normalize_waive_reason(reason)

        await cls._require_report_belongs_to_task(
            db,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
        )

        assignment = (
            await ReportAssignmentRepo.get_assignment_for_update(
                db,
                selected_report_id=selected_report_id,
            )
        )

        if assignment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Назначение выбранного отчёта не найдено.",
            )

        current_status = cls._normalize_status(
            getattr(assignment, "status", None)
        )

        if current_status == ReportAssignmentStatus.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Выполненный отчёт нельзя освободить "
                    "от выполнения."
                ),
            )

        return await ReportAssignmentRepo.waive(
            db,
            assignment=assignment,
            reason=normalized_reason,
            waived_by_user_id=user_id,
        )

    @classmethod
    async def get_resolution_state(
        cls,
        db: AsyncSession,
        *,
        user: User,
        month_item_id: int,
    ) -> dict[str, int | bool]:
        """
        Получить состояние системных отчётов задачи.

        Метод используется ответственным для проверки,
        можно ли переходить к итоговому документу.
        """

        _, _, _, task = await cls._prepare_primary_action(
            db,
            user=user,
            month_item_id=month_item_id,
        )

        cls._require_task_in_progress(task)

        reports = await ReportAssignmentRepo.list_report_rows(
            db,
            month_item_id=month_item_id,
        )

        report_count = len(reports)
        assigned_count = sum(
            1
            for report in reports
            if report.is_assigned
        )
        pending_count = sum(
            1
            for report in reports
            if report.is_pending
        )
        completed_count = sum(
            1
            for report in reports
            if report.is_completed
        )
        waived_count = sum(
            1
            for report in reports
            if report.is_waived
        )

        has_reports = report_count > 0

        all_assigned = (
                has_reports
                and assigned_count == report_count
        )

        all_resolved = (
                has_reports
                and all(report.is_resolved for report in reports)
        )

        return {
            "report_count": report_count,
            "assigned_count": assigned_count,
            "pending_count": pending_count,
            "completed_count": completed_count,
            "waived_count": waived_count,
            "all_assigned": all_assigned,
            "all_resolved": all_resolved,
        }

    # =========================================================
    # ACTION PREPARATION
    # =========================================================

    @classmethod
    async def _prepare_primary_action(
        cls,
        db: AsyncSession,
        *,
        user: User,
        month_item_id: int,
    ):
        """
        Общая подготовка операции ответственного:

        - контекст пользователя;
        - активные роли;
        - проверка PRIMARY;
        - получение доступной задачи.
        """

        school_id, user_id = cls._require_user_context(user)

        role_ids = await cls._get_active_role_ids(
            db,
            user_id=user_id,
        )

        await cls._require_primary_executor(
            db,
            month_item_id=month_item_id,
            school_id=school_id,
            staff_role_ids=role_ids,
        )

        task = await cls._get_accessible_task(
            db,
            school_id=school_id,
            staff_role_ids=role_ids,
            month_item_id=month_item_id,
        )

        return school_id, user_id, role_ids, task

    @staticmethod
    async def _require_report_belongs_to_task(
        db: AsyncSession,
        *,
        month_item_id: int,
        selected_report_id: int,
    ) -> None:
        """
        Проверить, что selected_report_id относится
        к текущей задаче.
        """

        rows = await ReportAssignmentRepo.list_report_rows(db, month_item_id=month_item_id)
        selected_report_ids = {row.selected_report_id for row in rows if row.assignable}
        invalid = next((row for row in rows if row.selected_report_id == selected_report_id and not row.assignable), None)
        if invalid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=invalid.target_error)


        if selected_report_id not in selected_report_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Выбранный отчёт не относится "
                    "к указанной задаче."
                ),
            )

    @staticmethod
    async def _require_allowed_staff_member(
        db: AsyncSession,
        *,
        month_item_id: int,
        school_id: int,
        staff_member_id: int,
    ) -> None:
        """
        Проверить, что новый исполнитель назначен
        на задачу как PRIMARY или CO_EXECUTOR.
        """

        allowed_staff_member_ids = (
            await ReportAssignmentRepo.get_allowed_staff_member_ids(
                db,
                month_item_id=month_item_id,
                school_id=school_id,
            )
        )

        if staff_member_id not in allowed_staff_member_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Выбранный сотрудник не является "
                    "исполнителем этой задачи."
                ),
            )

    @staticmethod
    def _require_positive_id(
        value: int,
        *,
        field_name: str,
    ) -> int:
        """
        Нормализовать положительный идентификатор.
        """

        normalized = int(value)

        if normalized <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Некорректный идентификатор {field_name}."
                ),
            )

        return normalized

    @staticmethod
    def _normalize_waive_reason(
        reason: str,
    ) -> str:
        """
        Проверить и нормализовать причину освобождения.
        """

        normalized = str(
            reason or ""
        ).strip()

        if not normalized:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Укажите причину завершения задачи "
                    "без этого отчёта."
                ),
            )

        if len(normalized) > 2000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Причина слишком длинная. "
                    "Максимум 2000 символов."
                ),
            )

        return normalized

    # =========================================================
    # VALIDATION
    # =========================================================

    @staticmethod
    def _require_user_context(
        user: User,
    ) -> tuple[int, int]:
        """
        Получить school_id и user_id.

        Без этих значений операция распределения
        отчётов недоступна.
        """

        school_id = getattr(
            user,
            "school_id",
            None,
        )

        user_id = getattr(
            user,
            "id",
            None,
        )

        if school_id is None or user_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Недостаточно данных пользователя "
                    "для распределения отчётов."
                ),
            )

        return int(school_id), int(user_id)

    @staticmethod
    async def _get_active_role_ids(
        db: AsyncSession,
        *,
        user_id: int,
    ) -> list[int]:
        """
        Получить активные должностные роли пользователя.
        """

        role_ids = await (
            SchoolStaffRepo
            .get_active_role_ids_by_user_id(
                db,
                user_id=user_id,
            )
        )

        normalized_role_ids = [
            int(role_id)
            for role_id in role_ids
        ]

        if not normalized_role_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "У пользователя нет активной роли "
                    "сотрудника школы."
                ),
            )

        return normalized_role_ids

    @staticmethod
    async def _require_primary_executor(
        db: AsyncSession,
        *,
        month_item_id: int,
        school_id: int,
        staff_role_ids: Sequence[int],
    ) -> None:
        """
        Проверить, что текущий сотрудник назначен
        ответственным PRIMARY этой задачи.
        """

        is_primary = await (
            ReportAssignmentRepo
            .is_primary_executor(
                db,
                month_item_id=month_item_id,
                school_id=school_id,
                staff_role_ids=staff_role_ids,
            )
        )

        if not is_primary:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Распределять отчёты может только "
                    "ответственный исполнитель задачи."
                ),
            )

    @staticmethod
    async def _get_accessible_task(
        db: AsyncSession,
        *,
        school_id: int,
        staff_role_ids: Sequence[int],
        month_item_id: int,
    ):
        """
        Получить задачу с проверкой школы и назначения
        текущего сотрудника.

        Используется существующий репозиторный метод страницы
        исполнения, поскольку он загружает данные задачи
        и её связанные сущности.
        """

        task = await StaffTasksRepo.get_task_for_execution(
            db,
            school_id=school_id,
            staff_role_ids=list(staff_role_ids),
            month_item_id=month_item_id,
        )

        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "Задача не найдена или недоступна "
                    "текущему пользователю."
                ),
            )

        return task

    @classmethod
    def _require_task_in_progress(
        cls,
        task,
    ) -> None:
        """
        Проверить, что задача принята в исполнение.

        Распределение отчётов разрешается для IN_PROGRESS.

        При необходимости позже сюда можно добавить DONE,
        если будет разрешено изменять распределение после
        завершения задачи.
        """

        task_status = cls._normalize_status(
            getattr(task, "status", None)
        )

        if task_status != PlanItemStatus.IN_PROGRESS.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Распределять отчёты можно только после "
                    "принятия задачи в исполнение."
                ),
            )

    @staticmethod
    def _normalize_assignment_inputs(
        assignments: Sequence[
            ReportAssignmentInputDTO
        ],
    ) -> dict[int, int]:
        """
        Нормализовать POST-данные формы.

        Возвращает словарь:

            selected_report_id -> staff_member_id

        Повтор одного selected_report_id считается ошибкой,
        даже если staff_member_id совпадает.
        """

        normalized: dict[int, int] = {}

        for assignment in assignments:
            selected_report_id = int(
                assignment.selected_report_id
            )

            staff_member_id = int(
                assignment.staff_member_id
            )

            if selected_report_id <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Получен некорректный идентификатор "
                        "выбранного отчёта."
                    ),
                )

            if staff_member_id <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Получен некорректный идентификатор "
                        "исполнителя отчёта."
                    ),
                )

            if selected_report_id in normalized:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Один и тот же отчёт передан "
                        "в форме несколько раз."
                    ),
                )

            normalized[selected_report_id] = (
                staff_member_id
            )

        return normalized

    @staticmethod
    def _validate_complete_report_set(
        *,
        submitted_report_ids: set[int],
        expected_report_ids: set[int],
    ) -> None:
        """
        Проверить, что форма содержит распределение
        для каждого выбранного отчёта задачи.

        Лишние отчёты также запрещены.
        """

        foreign_report_ids = (
            submitted_report_ids
            - expected_report_ids
        )

        if foreign_report_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Форма содержит отчёты, которые "
                    "не относятся к выбранной задаче."
                ),
            )

        missing_report_ids = (
            expected_report_ids
            - submitted_report_ids
        )

        if missing_report_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Назначьте исполнителя каждому "
                    "выбранному отчёту."
                ),
            )

    @staticmethod
    def _validate_assigned_staff(
        *,
        assignments: dict[int, int],
        allowed_staff_member_ids: set[int],
    ) -> None:
        """
        Проверить, что все выбранные исполнители назначены
        на эту задачу как PRIMARY или CO_EXECUTOR.
        """

        if not allowed_staff_member_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "У задачи нет доступных исполнителей "
                    "для распределения отчётов."
                ),
            )

        submitted_staff_ids = set(
            assignments.values()
        )

        foreign_staff_ids = (
            submitted_staff_ids
            - allowed_staff_member_ids
        )

        if foreign_staff_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Один или несколько выбранных сотрудников "
                    "не назначены исполнителями этой задачи."
                ),
            )

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _normalize_status(
        raw_status,
    ) -> str:
        """
        Нормализовать ORM Enum или строку статуса.
        """

        if raw_status is None:
            return ""

        raw_value = getattr(
            raw_status,
            "value",
            raw_status,
        )

        return str(raw_value)

    @staticmethod
    def _format_period(
        planned_start: date | None,
        planned_end: date | None,
    ) -> str:
        """
        Сформировать период задачи для страницы.
        """

        if planned_start and planned_end:
            if planned_start == planned_end:
                return planned_start.strftime(
                    "%d.%m.%Y"
                )

            return (
                f"{planned_start:%d.%m.%Y} – "
                f"{planned_end:%d.%m.%Y}"
            )

        if planned_start:
            return (
                f"с {planned_start:%d.%m.%Y}"
            )

        if planned_end:
            return (
                f"до {planned_end:%d.%m.%Y}"
            )

        return "—"
