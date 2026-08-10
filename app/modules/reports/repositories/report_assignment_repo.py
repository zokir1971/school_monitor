# app/modules/reports/repositories/report_assignment_repo.py

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.planning.enums import AssignmentKind
from app.modules.planning.models_month_plan import (
    SchoolMonthPlan,
    SchoolMonthPlanItem,
    SchoolMonthPlanItemAssignee,
)
from app.modules.planning.models_school import (
    SchoolPlan,
    SchoolPlanRow11,
)
from app.modules.reports.control_flow import is_report_target_assignable
from app.modules.reports.enums import ReportAssignmentStatus
from app.modules.reports.models_documents import (
    ReportTypeModel,
    TaskExecutionData,
    TaskExecutionSelectedReport,
)
from app.modules.reports.models_report_assignments import (
    TaskSelectedReportAssignment,
)
from app.modules.reports.schemas.report_assignment_dto import (
    ReportAssignmentExecutorDTO,
    ReportAssignmentRowDTO,
)
from app.modules.staff.models_staff_school import (
    SchoolStaffMember,
    SchoolStaffRole,
)


class ReportAssignmentRepo:
    """
    Репозиторий распределения выбранных системных отчётов.

    Репозиторий отвечает только за работу с данными:

    - получает выбранные отчёты задачи;
    - получает допустимых исполнителей задачи;
    - получает существующие назначения;
    - блокирует записи перед изменением;
    - создаёт, обновляет и удаляет назначения.

    Проверки бизнес-правил выполняются сервисом.
    """

    # =========================================================
    # PAGE DATA
    # =========================================================

    @staticmethod
    async def list_executor_choices(
        db: AsyncSession,
        *,
        month_item_id: int,
        school_id: int,
    ) -> list[ReportAssignmentExecutorDTO]:
        """
        Получить сотрудников, которым разрешено назначать
        выбранные отчёты задачи.

        В выборку входят только активные сотрудники школы,
        назначенные на задачу как:

        - PRIMARY;
        - CO_EXECUTOR.

        Один сотрудник возвращается один раз. Если из-за
        некорректных данных он имеет оба вида назначения,
        приоритет отдаётся PRIMARY.
        """

        stmt = (
            select(
                SchoolStaffMember.id.label(
                    "staff_member_id"
                ),
                SchoolStaffMember.full_name.label(
                    "full_name"
                ),
                SchoolStaffMember.position_text.label(
                    "position_text"
                ),
                SchoolMonthPlanItemAssignee.assignment_kind.label(
                    "assignment_kind"
                ),
            )
            .select_from(
                SchoolMonthPlanItemAssignee
            )
            .join(
                SchoolStaffRole,
                SchoolStaffRole.id
                == SchoolMonthPlanItemAssignee.staff_role_id,
            )
            .join(
                SchoolStaffMember,
                SchoolStaffMember.id
                == SchoolStaffRole.staff_member_id,
            )
            .where(
                SchoolMonthPlanItemAssignee.month_item_id
                == month_item_id,

                SchoolStaffRole.school_id
                == school_id,

                SchoolStaffRole.is_active.is_(True),

                SchoolStaffMember.school_id
                == school_id,

                SchoolStaffMember.is_active.is_(True),

                SchoolMonthPlanItemAssignee.assignment_kind.in_(
                    [
                        AssignmentKind.PRIMARY,
                        AssignmentKind.CO_EXECUTOR,
                    ]
                ),
            )
            .order_by(
                SchoolStaffMember.full_name.asc(),
                SchoolStaffMember.id.asc(),
            )
        )

        rows = (
            await db.execute(stmt)
        ).all()

        executors_by_staff: dict[
            int,
            ReportAssignmentExecutorDTO,
        ] = {}

        for row in rows:
            staff_member_id = int(
                row.staff_member_id
            )

            assignment_kind = (
                row.assignment_kind
                if isinstance(
                    row.assignment_kind,
                    AssignmentKind,
                )
                else AssignmentKind(
                    getattr(
                        row.assignment_kind,
                        "value",
                        row.assignment_kind,
                    )
                )
            )

            existing = executors_by_staff.get(
                staff_member_id
            )

            # Если сотрудник уже найден как PRIMARY,
            # более слабое назначение не заменяет его.
            if (
                existing is not None
                and existing.is_primary
            ):
                continue

            is_primary = (
                assignment_kind
                == AssignmentKind.PRIMARY
            )

            is_co_executor = (
                assignment_kind
                == AssignmentKind.CO_EXECUTOR
            )

            executors_by_staff[staff_member_id] = (
                ReportAssignmentExecutorDTO(
                    staff_member_id=staff_member_id,
                    full_name=str(
                        row.full_name or "—"
                    ),
                    position_text=(
                        str(row.position_text)
                        if row.position_text
                        else None
                    ),
                    assignment_kind=assignment_kind.value,
                    assignment_kind_label=(
                        ReportAssignmentRepo
                        ._assignment_kind_label(
                            assignment_kind
                        )
                    ),
                    is_primary=is_primary,
                    is_co_executor=is_co_executor,
                )
            )

        return sorted(
            executors_by_staff.values(),
            key=lambda executor: (
                not executor.is_primary,
                executor.full_name.casefold(),
                executor.staff_member_id,
            ),
        )

    @staticmethod
    async def list_report_rows(
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> list[ReportAssignmentRowDTO]:
        """
        Получить выбранные системные отчёты задачи
        вместе с текущим назначением исполнителя.

        Возвращает также состояние назначения:

        - PENDING;
        - COMPLETED;
        - WAIVED.

        Если назначение ещё не создано,
        поля назначения будут равны None.
        """

        assigned_staff = aliased(
            SchoolStaffMember
        )

        stmt = (
            select(
                TaskExecutionSelectedReport.id.label(
                    "selected_report_id"
                ),

                TaskExecutionSelectedReport.report_type_id.label(
                    "report_type_id"
                ),

                ReportTypeModel.code.label(
                    "report_code"
                ),

                func.coalesce(
                    ReportTypeModel.name_ru,
                    ReportTypeModel.name_kz,
                    ReportTypeModel.code,
                ).label(
                    "report_name"
                ),

                TaskExecutionSelectedReport.target_kind.label(
                    "target_kind"
                ),

                TaskExecutionSelectedReport.target_value.label(
                    "target_value"
                ),

                TaskExecutionSelectedReport.target_label.label(
                    "target_label"
                ),

                # Текущий исполнитель
                TaskSelectedReportAssignment.staff_member_id.label(
                    "assigned_staff_member_id"
                ),

                assigned_staff.full_name.label(
                    "assigned_staff_full_name"
                ),

                TaskSelectedReportAssignment.assigned_at.label(
                    "assigned_at"
                ),

                TaskSelectedReportAssignment.assigned_by_user_id.label(
                    "assigned_by_user_id"
                ),

                # Состояние назначения
                TaskSelectedReportAssignment.status.label(
                    "assignment_status"
                ),

                # Освобождение от отчёта
                TaskSelectedReportAssignment.waived_reason.label(
                    "waived_reason"
                ),

                TaskSelectedReportAssignment.waived_by_user_id.label(
                    "waived_by_user_id"
                ),

                TaskSelectedReportAssignment.waived_at.label(
                    "waived_at"
                ),
            )

            .select_from(
                TaskExecutionSelectedReport
            )

            .join(
                TaskExecutionData,
                TaskExecutionData.id
                == TaskExecutionSelectedReport.execution_data_id,
            )

            .join(
                ReportTypeModel,
                ReportTypeModel.id
                == TaskExecutionSelectedReport.report_type_id,
            )

            .outerjoin(
                TaskSelectedReportAssignment,
                (
                        TaskSelectedReportAssignment.selected_report_id
                        == TaskExecutionSelectedReport.id
                ),
            )

            .outerjoin(
                assigned_staff,
                assigned_staff.id
                == TaskSelectedReportAssignment.staff_member_id,
            )

            .where(
                TaskExecutionData.month_item_id
                == month_item_id,
            )

            .order_by(
                ReportTypeModel.sort_order.asc(),
                ReportTypeModel.id.asc(),
                TaskExecutionSelectedReport.target_label.asc()
                .nulls_last(),
                TaskExecutionSelectedReport.id.asc(),
            )
        )

        rows = (
            await db.execute(stmt)
        ).all()

        result: list[ReportAssignmentRowDTO] = []

        for row in rows:
            report_code = str(
                row.report_code or ""
            )

            target_kind = str(
                row.target_kind or ""
            )

            # Родительская или неподходящая строка отчёта
            # не участвует в распределении.
            if not is_report_target_assignable(
                    report_code=report_code,
                    target_kind=target_kind,
            ):
                continue

            assignment_status = (
                row.assignment_status
                if isinstance(
                    row.assignment_status,
                    ReportAssignmentStatus,
                )
                else (
                    ReportAssignmentStatus(
                        getattr(
                            row.assignment_status,
                            "value",
                            row.assignment_status,
                        )
                    )
                    if row.assignment_status is not None
                    else None
                )
            )

            result.append(
                ReportAssignmentRowDTO(
                    selected_report_id=int(
                        row.selected_report_id
                    ),

                    report_type_id=int(
                        row.report_type_id
                    ),

                    report_code=report_code,

                    report_name=str(
                        row.report_name or "—"
                    ),

                    target_kind=target_kind,

                    target_value=str(
                        row.target_value or ""
                    ),

                    target_label=str(
                        row.target_label
                        or row.target_value
                        or "—"
                    ),

                    assigned_staff_member_id=(
                        int(row.assigned_staff_member_id)
                        if row.assigned_staff_member_id is not None
                        else None
                    ),

                    assigned_staff_full_name=(
                        str(row.assigned_staff_full_name)
                        if row.assigned_staff_full_name
                        else None
                    ),

                    assigned_at=row.assigned_at,

                    assigned_by_user_id=(
                        int(row.assigned_by_user_id)
                        if row.assigned_by_user_id is not None
                        else None
                    ),

                    assignment_status=(
                        assignment_status.value
                        if assignment_status is not None
                        else None
                    ),

                    assignment_status_label=(
                        getattr(
                            assignment_status,
                            "label_kz",
                            assignment_status.value,
                        )
                        if assignment_status is not None
                        else None
                    ),

                    waived_reason=(
                        str(row.waived_reason)
                        if row.waived_reason
                        else None
                    ),

                    waived_by_user_id=(
                        int(row.waived_by_user_id)
                        if row.waived_by_user_id is not None
                        else None
                    ),

                    waived_at=row.waived_at,
                )
            )

        return result

    # =========================================================
    # VALIDATION DATA
    # =========================================================

    @staticmethod
    async def get_allowed_staff_member_ids(
        db: AsyncSession,
        *,
        month_item_id: int,
        school_id: int,
    ) -> set[int]:
        """
        Получить ID сотрудников, которым можно назначить
        отчёты указанной задачи.

        Используется сервисом для защиты от назначения
        отчёта постороннему сотруднику.
        """

        stmt = (
            select(
                SchoolStaffMember.id
            )
            .select_from(
                SchoolMonthPlanItemAssignee
            )
            .join(
                SchoolStaffRole,
                SchoolStaffRole.id
                == SchoolMonthPlanItemAssignee.staff_role_id,
            )
            .join(
                SchoolStaffMember,
                SchoolStaffMember.id
                == SchoolStaffRole.staff_member_id,
            )
            .where(
                SchoolMonthPlanItemAssignee.month_item_id
                == month_item_id,

                SchoolStaffRole.school_id
                == school_id,

                SchoolStaffRole.is_active.is_(True),

                SchoolStaffMember.school_id
                == school_id,

                SchoolStaffMember.is_active.is_(True),

                SchoolMonthPlanItemAssignee.assignment_kind.in_(
                    [
                        AssignmentKind.PRIMARY,
                        AssignmentKind.CO_EXECUTOR,
                    ]
                ),
            )
            .distinct()
        )

        result = await db.execute(stmt)

        return {
            int(staff_member_id)
            for staff_member_id
            in result.scalars().all()
        }

    @staticmethod
    async def get_selected_report_ids(
        db: AsyncSession,
        *,
        month_item_id: int,
    ) -> set[int]:
        """
        Получить ID всех выбранных отчётов задачи.

        Используется сервисом для проверки, что POST-запрос
        не содержит отчёты другой задачи.
        """

        stmt = (
            select(
                TaskExecutionSelectedReport.id
            )
            .join(
                TaskExecutionData,
                TaskExecutionData.id
                == TaskExecutionSelectedReport.execution_data_id,
            )
            .where(
                TaskExecutionData.month_item_id
                == month_item_id,
            )
        )

        result = await db.execute(stmt)

        return {
            int(selected_report_id)
            for selected_report_id
            in result.scalars().all()
        }

    @staticmethod
    async def is_primary_executor(
        db: AsyncSession,
        *,
        month_item_id: int,
        school_id: int,
        staff_role_ids: Sequence[int],
    ) -> bool:
        """
        Проверить, назначен ли текущий сотрудник ответственным
        PRIMARY для указанной задачи.

        Метод не проверяет роль пользователя в системе.
        Он проверяет только назначение сотрудника на задачу.
        """

        if not staff_role_ids:
            return False

        stmt = (
            select(
                SchoolMonthPlanItemAssignee.id
            )
            .join(
                SchoolStaffRole,
                SchoolStaffRole.id
                == SchoolMonthPlanItemAssignee.staff_role_id,
            )
            .where(
                SchoolMonthPlanItemAssignee.month_item_id
                == month_item_id,

                SchoolMonthPlanItemAssignee.staff_role_id.in_(
                    list(staff_role_ids)
                ),

                SchoolMonthPlanItemAssignee.assignment_kind
                == AssignmentKind.PRIMARY,

                SchoolStaffRole.school_id
                == school_id,

                SchoolStaffRole.is_active.is_(True),
            )
            .limit(1)
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none() is not None

    # =========================================================
    # STAFF REPORT WORKSPACE
    # =========================================================

    @staticmethod
    async def list_report_tasks_for_staff(
        db: AsyncSession,
        *,
        school_id: int,
        staff_member_id: int,
        month: int,
    ) -> list[dict[str, Any]]:
        """
        Получить задачи выбранного месяца, в которых текущему
        сотруднику назначен хотя бы один выбранный отчет.

        Это выборка для быстрого входа сотрудника в заполнение
        отчетов с панели без повторного прохождения алгоритма
        исполнения задачи.

        Цепочка данных:

            TaskSelectedReportAssignment
                -> TaskExecutionSelectedReport
                -> TaskExecutionData
                -> SchoolMonthPlanItem
                -> SchoolMonthPlan
                -> SchoolPlan

        В выборку НЕ попадают просто задачи, где сотрудник является
        PRIMARY/CO_EXECUTOR. Попадают только задачи, где конкретно
        существует назначение отчета на staff_member_id.

        Репозиторий возвращает только данные. Формирование period_text,
        подписей статуса и DTO выполняется сервисом.
        """

        stmt = (
            select(
                SchoolMonthPlanItem.id.label("month_item_id"),
                SchoolMonthPlanItem.week_of_month.label("week_of_month"),
                SchoolMonthPlanItem.planned_start.label("planned_start"),
                SchoolMonthPlanItem.planned_end.label("planned_end"),
                SchoolMonthPlanItem.status.label("task_status"),
                SchoolPlanRow11.topic.label("topic"),
                func.count(
                    func.distinct(
                        TaskSelectedReportAssignment.selected_report_id
                    )
                ).label("assigned_reports_count"),
            )
            .select_from(TaskSelectedReportAssignment)
            .join(
                TaskExecutionSelectedReport,
                TaskExecutionSelectedReport.id
                == TaskSelectedReportAssignment.selected_report_id,
            )
            .join(
                TaskExecutionData,
                TaskExecutionData.id
                == TaskExecutionSelectedReport.execution_data_id,
            )
            .join(
                SchoolMonthPlanItem,
                SchoolMonthPlanItem.id
                == TaskExecutionData.month_item_id,
            )
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )
            .join(
                SchoolPlan,
                SchoolPlan.id
                == SchoolMonthPlan.school_plan_id,
            )
            .outerjoin(
                SchoolPlanRow11,
                SchoolPlanRow11.id
                == SchoolMonthPlanItem.source_row11_id,
            )
            .where(
                TaskSelectedReportAssignment.staff_member_id
                == staff_member_id,
                SchoolPlan.school_id == school_id,
                SchoolMonthPlan.month == month,
                SchoolMonthPlanItem.is_included.is_(True),
            )
            .group_by(
                SchoolMonthPlanItem.id,
                SchoolMonthPlanItem.week_of_month,
                SchoolMonthPlanItem.planned_start,
                SchoolMonthPlanItem.planned_end,
                SchoolMonthPlanItem.status,
                SchoolPlanRow11.topic,
            )
            .order_by(
                SchoolMonthPlanItem.planned_start.asc().nulls_last(),
                SchoolMonthPlanItem.planned_end.asc().nulls_last(),
                SchoolMonthPlanItem.id.asc(),
            )
        )

        rows = (await db.execute(stmt)).mappings().all()

        return [
            {
                "month_item_id": int(row["month_item_id"]),
                "week_of_month": row["week_of_month"],
                "planned_start": row["planned_start"],
                "planned_end": row["planned_end"],
                "topic": str(row["topic"] or "—"),
                "task_status": row["task_status"],
                "assigned_reports_count": int(
                    row["assigned_reports_count"] or 0
                ),
            }
            for row in rows
        ]

    @staticmethod
    async def has_report_assignment_for_task(
        db: AsyncSession,
        *,
        school_id: int,
        staff_member_id: int,
        month_item_id: int,
    ) -> bool:
        """
        Проверить, назначен ли текущему сотруднику хотя бы один
        отчет указанной задачи.

        Используется перед redirect с быстрого рабочего экрана
        на /staff/reports/{month_item_id}/templates.

        Одновременно проверяется принадлежность задачи школе,
        поэтому подстановка чужого month_item_id в query-параметр
        не дает доступ к чужой задаче.
        """

        stmt = (
            select(TaskSelectedReportAssignment.id)
            .select_from(TaskSelectedReportAssignment)
            .join(
                TaskExecutionSelectedReport,
                TaskExecutionSelectedReport.id
                == TaskSelectedReportAssignment.selected_report_id,
            )
            .join(
                TaskExecutionData,
                TaskExecutionData.id
                == TaskExecutionSelectedReport.execution_data_id,
            )
            .join(
                SchoolMonthPlanItem,
                SchoolMonthPlanItem.id
                == TaskExecutionData.month_item_id,
            )
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )
            .join(
                SchoolPlan,
                SchoolPlan.id
                == SchoolMonthPlan.school_plan_id,
            )
            .where(
                TaskSelectedReportAssignment.staff_member_id
                == staff_member_id,
                TaskExecutionData.month_item_id == month_item_id,
                SchoolPlan.school_id == school_id,
                SchoolMonthPlanItem.is_included.is_(True),
            )
            .limit(1)
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None

    # =========================================================
    # LOCKING
    # =========================================================

    @staticmethod
    async def list_assignments_for_update(
        db: AsyncSession,
        *,
        selected_report_ids: Sequence[int],
    ) -> list[TaskSelectedReportAssignment]:
        """
        Получить и заблокировать существующие назначения
        выбранных отчётов.

        Используется при пакетном сохранении распределения,
        чтобы параллельные запросы не перезаписали друг друга.
        """

        if not selected_report_ids:
            return []

        stmt = (
            select(
                TaskSelectedReportAssignment
            )
            .where(
                TaskSelectedReportAssignment.selected_report_id.in_(
                    list(selected_report_ids)
                )
            )
            .with_for_update()
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    @staticmethod
    async def get_assignment_for_update(
        db: AsyncSession,
        *,
        selected_report_id: int,
    ) -> TaskSelectedReportAssignment | None:
        """
        Получить одно назначение с блокировкой строки.
        """

        stmt = (
            select(
                TaskSelectedReportAssignment
            )
            .where(
                TaskSelectedReportAssignment.selected_report_id
                == selected_report_id
            )
            .with_for_update()
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    # =========================================================
    # CREATE / UPDATE / DELETE
    # =========================================================

    @staticmethod
    async def create(
            db: AsyncSession,
            *,
            selected_report_id: int,
            staff_member_id: int,
            assigned_by_user_id: int,
    ) -> TaskSelectedReportAssignment:
        """
        Создать назначение исполнителя выбранному отчёту.

        Новое назначение всегда начинает жизненный цикл
        со статуса PENDING.

        Commit выполняется сервисом или маршрутом.
        """

        assignment = TaskSelectedReportAssignment(
            selected_report_id=selected_report_id,
            staff_member_id=staff_member_id,
            assigned_by_user_id=assigned_by_user_id,
            status=ReportAssignmentStatus.PENDING,
        )

        db.add(assignment)

        await db.flush()

        return assignment

    @staticmethod
    async def update_executor(
            db: AsyncSession,
            *,
            assignment: TaskSelectedReportAssignment,
            staff_member_id: int,
            assigned_by_user_id: int,
    ) -> TaskSelectedReportAssignment:
        """
        Переназначить выбранный отчёт другому исполнителю.

        При переназначении:

        - меняется текущий исполнитель;
        - фиксируется пользователь, выполнивший переназначение;
        - назначение снова становится PENDING;
        - очищаются данные WAIVED;
        - assigned_at становится временем нового назначения.

        История переназначения будет храниться отдельно.
        """

        assignment.staff_member_id = staff_member_id

        assignment.assigned_by_user_id = (
            assigned_by_user_id
        )

        assignment.assigned_at = datetime.now(
            timezone.utc
        )

        assignment.status = (
            ReportAssignmentStatus.PENDING
        )

        assignment.waived_reason = None
        assignment.waived_by_user_id = None
        assignment.waived_at = None

        await db.flush()

        return assignment

    @staticmethod
    async def delete(
        db: AsyncSession,
        *,
        assignment: TaskSelectedReportAssignment,
    ) -> None:
        """
        Удалить назначение выбранного отчёта.

        Сам выбранный отчёт при этом не удаляется.
        """

        await db.delete(assignment)
        await db.flush()

    @staticmethod
    async def delete_by_selected_report_ids(
        db: AsyncSession,
        *,
        selected_report_ids: Sequence[int],
    ) -> int:
        """
        Удалить назначения указанных выбранных отчётов.

        Метод используется, если форма допускает оставить
        отчёт без исполнителя.
        """

        if not selected_report_ids:
            return 0

        assignments = await (
            ReportAssignmentRepo
            .list_assignments_for_update(
                db,
                selected_report_ids=selected_report_ids,
            )
        )

        for assignment in assignments:
            await db.delete(assignment)

        await db.flush()

        return len(assignments)

    # =========================================================
    # CO-EXECUTOR QUERIES
    # =========================================================

    @staticmethod
    async def count_reports_for_staff(
        db: AsyncSession,
        *,
        month_item_id: int,
        staff_member_id: int,
    ) -> int:
        """
        Посчитать выбранные отчёты задачи, назначенные
        конкретному сотруднику.

        Этот метод позже можно использовать для построения
        CoExecutorTaskDTO.
        """

        stmt = (
            select(
                func.count(
                    TaskSelectedReportAssignment.id
                )
            )
            .select_from(
                TaskSelectedReportAssignment
            )
            .join(
                TaskExecutionSelectedReport,
                TaskExecutionSelectedReport.id
                == TaskSelectedReportAssignment.selected_report_id,
            )
            .join(
                TaskExecutionData,
                TaskExecutionData.id
                == TaskExecutionSelectedReport.execution_data_id,
            )
            .where(
                TaskExecutionData.month_item_id
                == month_item_id,
                TaskSelectedReportAssignment.staff_member_id
                == staff_member_id,
            )
        )

        result = await db.execute(stmt)

        return int(
            result.scalar_one() or 0
        )

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _assignment_kind_label(
        assignment_kind: AssignmentKind,
    ) -> str:
        """
        Получить подпись вида назначения.

        Сначала используются подписи Enum, если они
        предусмотрены в проекте.
        """

        enum_label = (
            getattr(
                assignment_kind,
                "label_ru",
                None,
            )
            or getattr(
                assignment_kind,
                "label_kz",
                None,
            )
            or getattr(
                assignment_kind,
                "label",
                None,
            )
        )

        if enum_label:
            return str(enum_label)

        if assignment_kind == AssignmentKind.PRIMARY:
            return "Ответственный"

        if (
            assignment_kind
            == AssignmentKind.CO_EXECUTOR
        ):
            return "Соисполнитель"

        return "Исполнитель"

    @staticmethod
    async def waive(
            db: AsyncSession,
            *,
            assignment: TaskSelectedReportAssignment,
            reason: str,
            waived_by_user_id: int,
    ) -> TaskSelectedReportAssignment:
        """
        Освободить назначенный отчёт от обязательного выполнения.

        Используется ответственным, когда задачу необходимо
        завершить без конкретного системного отчёта.

        Проверка права пользователя и обязательности причины
        выполняется сервисом.
        """

        assignment.status = (
            ReportAssignmentStatus.WAIVED
        )

        assignment.waived_reason = reason

        assignment.waived_by_user_id = (
            waived_by_user_id
        )

        assignment.waived_at = datetime.now(
            timezone.utc
        )

        await db.flush()

        return assignment

    @staticmethod
    async def mark_completed(
            db: AsyncSession,
            *,
            assignment: TaskSelectedReportAssignment,
    ) -> TaskSelectedReportAssignment:
        """
        Отметить назначение отчёта как выполненное.

        Вызывается после успешного завершения
        соответствующего системного отчёта.
        """

        assignment.status = (
            ReportAssignmentStatus.COMPLETED
        )

        assignment.waived_reason = None
        assignment.waived_by_user_id = None
        assignment.waived_at = None

        await db.flush()

        return assignment

    @staticmethod
    async def has_pending_assignments(
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> bool:
        """
        Проверить, существуют ли у задачи отчёты,
        которые всё ещё ожидают выполнения.
        """

        stmt = (
            select(TaskSelectedReportAssignment.id)
            .select_from(TaskSelectedReportAssignment)
            .join(
                TaskExecutionSelectedReport,
                TaskExecutionSelectedReport.id
                == TaskSelectedReportAssignment.selected_report_id,
            )
            .join(
                TaskExecutionData,
                TaskExecutionData.id
                == TaskExecutionSelectedReport.execution_data_id,
            )
            .where(
                TaskExecutionData.month_item_id
                == month_item_id,

                TaskSelectedReportAssignment.status
                == ReportAssignmentStatus.PENDING,
            )
            .limit(1)
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none() is not None
