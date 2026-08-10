# app/modules/monitoring/monitoring_repo.py

from __future__ import annotations

from sqlalchemy import (
    String,
    case,
    cast,
    func,
    literal,
    select,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import PlanItemStatus
from app.modules.planning.models_month_plan import (
    SchoolMonthPlan,
    SchoolMonthPlanItem,
    SchoolMonthPlanItemAssignee,
)
from app.modules.planning.models_school import SchoolPlanRow11
from app.modules.reports.enums import (
    DocumentType,
    ReportAssignmentStatus,
    TaskDocumentStatus,
)
from app.modules.reports.models_documents import (
    TaskExecutionData,
    TaskExecutionDocument,
    TaskExecutionSelectedReport,
)
from app.modules.reports.models_report_assignments import (
    TaskSelectedReportAssignment,
)
from app.modules.staff.models_staff_school import (
    SchoolStaffMember,
    SchoolStaffRole,
)
from app.modules.users.models import User

from app.modules.monitoring.constants import (
    VALID_SCORE_DOCUMENT_STATUSES,
)


class StaffMonitoringRepository:
    """
    Репозиторий мониторинга результативности исполнителей.

    Возвращает исходные данные для расчёта рейтинга:

    - сотрудник;
    - задача;
    - признак выполнения;
    - наличие итогового документа;
    - персональные назначения отчётов;
    - количество выполненных, ожидающих и освобождённых отчётов.

    Начисление баллов выполняется в сервисном слое.
    """

    VALID_DOCUMENT_STATUSES = (
        TaskDocumentStatus.SUBMITTED,
        TaskDocumentStatus.APPROVED,
        TaskDocumentStatus.ACCEPTED,
    )

    # ------------------------------------------------------------------
    # Участники задач
    # ------------------------------------------------------------------

    @classmethod
    def _task_participants_subquery(cls):
        """
        Формирует уникальные пары:

            month_item_id + staff_member_id

        Также определяет вид участия сотрудника:

            primary
            co_executor

        Основной ответственный автоматически считается primary.

        Если сотрудник одновременно указан основным
        и соисполнителем, приоритет получает primary.
        """

        # Основной ответственный задачи.
        responsible_staff = (
            select(
                SchoolMonthPlanItem.id.label(
                    "month_item_id"
                ),
                User.staff_member_id.label(
                    "staff_member_id"
                ),
                literal("primary").label(
                    "assignment_kind"
                ),
            )
            .select_from(SchoolMonthPlanItem)
            .join(
                User,
                User.id
                == SchoolMonthPlanItem.responsible_user_id,
            )
            .where(
                SchoolMonthPlanItem.responsible_user_id.is_not(
                    None
                ),
                User.staff_member_id.is_not(None),
            )
        )

        # Исполнители и соисполнители,
        # назначенные через школьные роли.
        assigned_staff = (
            select(
                SchoolMonthPlanItemAssignee.month_item_id.label(
                    "month_item_id"
                ),
                SchoolStaffRole.staff_member_id.label(
                    "staff_member_id"
                ),
                cast(
                    SchoolMonthPlanItemAssignee.assignment_kind,
                    String,
                ).label("assignment_kind"),
            )
            .select_from(SchoolMonthPlanItemAssignee)
            .join(
                SchoolStaffRole,
                SchoolStaffRole.id
                == SchoolMonthPlanItemAssignee.staff_role_id,
            )
            .where(
                SchoolStaffRole.staff_member_id.is_not(None),
            )
        )

        all_participants = union_all(
            responsible_staff,
            assigned_staff,
        ).subquery("all_task_participants")

        # Убираем возможные дубли одного сотрудника в одной задаче.
        #
        # Если имеется хотя бы одна запись primary,
        # итоговая роль сотрудника — primary.
        return (
            select(
                all_participants.c.month_item_id,
                all_participants.c.staff_member_id,

                case(
                    (
                        func.max(
                            case(
                                (
                                    all_participants
                                    .c.assignment_kind
                                    == "primary",
                                    1,
                                ),
                                else_=0,
                            )
                        )
                        == 1,
                        "primary",
                    ),
                    else_="co_executor",
                ).label("assignment_kind"),
            )
            .group_by(
                all_participants.c.month_item_id,
                all_participants.c.staff_member_id,
            )
            .subquery("task_participants")
        )

    @classmethod
    def _task_final_document_subquery(cls):
        """
        Определяет наличие итогового документа
        для каждой задачи.

        Учитывается только текущая версия документа
        в допустимом статусе.
        """

        return (
            select(
                TaskExecutionDocument.month_item_id.label(
                    "month_item_id"
                ),

                func.max(
                    case(
                        (
                            TaskExecutionDocument.is_final.is_(
                                True
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("has_final_document"),
            )
            .where(
                TaskExecutionDocument.is_current.is_(True),

                TaskExecutionDocument.status.in_(
                    cls.VALID_DOCUMENT_STATUSES
                ),
            )
            .group_by(
                TaskExecutionDocument.month_item_id,
            )
            .subquery("task_final_documents")
        )

    @classmethod
    def _staff_report_assignment_statistics_subquery(cls):
        """
        Подсчитывает персональные назначения системных отчётов
        по каждой задаче и сотруднику.

        Источник истины:
            TaskSelectedReportAssignment.

        Цепочка данных:
            TaskSelectedReportAssignment
                -> TaskExecutionSelectedReport
                -> TaskExecutionData
                -> month_item_id

        Группировка:
            month_item_id + staff_member_id

        Статусы:
            PENDING
                отчёт назначен сотруднику и ещё ожидает выполнения;

            COMPLETED
                сотрудник выполнил назначенный отчёт;

            WAIVED
                сотрудник официально освобождён от выполнения отчёта.

        WAIVED закрывает обязательство задачи, но не считается
        выполненным отчётом сотрудника.
        """

        return (
            select(
                TaskExecutionData.month_item_id.label(
                    "month_item_id"
                ),

                TaskSelectedReportAssignment.staff_member_id.label(
                    "staff_member_id"
                ),

                func.count(
                    TaskSelectedReportAssignment.id
                ).label(
                    "assigned_report_count"
                ),

                func.count(
                    case(
                        (
                            TaskSelectedReportAssignment.status
                            == ReportAssignmentStatus.COMPLETED,
                            TaskSelectedReportAssignment.id,
                        )
                    )
                ).label(
                    "completed_report_count"
                ),

                func.count(
                    case(
                        (
                            TaskSelectedReportAssignment.status
                            == ReportAssignmentStatus.PENDING,
                            TaskSelectedReportAssignment.id,
                        )
                    )
                ).label(
                    "pending_report_count"
                ),

                func.count(
                    case(
                        (
                            TaskSelectedReportAssignment.status
                            == ReportAssignmentStatus.WAIVED,
                            TaskSelectedReportAssignment.id,
                        )
                    )
                ).label(
                    "waived_report_count"
                ),
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
            .group_by(
                TaskExecutionData.month_item_id,
                TaskSelectedReportAssignment.staff_member_id,
            )
            .subquery(
                "staff_report_assignment_statistics"
            )
        )

    # ------------------------------------------------------------------
    # Документы задачи
    # ------------------------------------------------------------------

    @classmethod
    def _task_document_statistics_subquery(cls):
        """
        Подсчитывает документы отдельно по каждой задаче.

        Учитываются только:

        - текущие версии документов;
        - отправленные, утверждённые или принятые документы.

        Итоговый документ:
            максимум 1 на задачу.

        Системный отчёт:
            document_type = REPORT
            custom_template_id IS NULL
            присутствует report_code или report_type_id.

        Пользовательский отчёт:
            document_type = REPORT
            custom_template_id IS NOT NULL.
        """

        is_report = (
                TaskExecutionDocument.document_type
                == DocumentType.REPORT
        )

        is_custom_report = (
                is_report
                & TaskExecutionDocument.custom_template_id.is_not(None)
        )

        is_system_report = (
                is_report
                & TaskExecutionDocument.custom_template_id.is_(None)
                & (
                        TaskExecutionDocument.report_code.is_not(None)
                        | TaskExecutionDocument.report_type_id.is_not(None)
                )
        )

        return (
            select(
                TaskExecutionDocument.month_item_id.label(
                    "month_item_id"
                ),

                # Итоговый документ считается максимум один раз.
                func.max(
                    case(
                        (
                            TaskExecutionDocument.is_final.is_(True),
                            1,
                        ),
                        else_=0,
                    )
                ).label("has_final_document"),

                # Количество системных отчётов.
                func.count(
                    case(
                        (
                            is_system_report,
                            TaskExecutionDocument.id,
                        )
                    )
                ).label("system_report_count"),

                # Количество пользовательских отчётов.
                func.count(
                    case(
                        (
                            is_custom_report,
                            TaskExecutionDocument.id,
                        )
                    )
                ).label("custom_report_count"),
            )
            .where(
                TaskExecutionDocument.is_current.is_(True),
                TaskExecutionDocument.status.in_(
                    VALID_SCORE_DOCUMENT_STATUSES
                ),
            )
            .group_by(
                TaskExecutionDocument.month_item_id,
            )
            .subquery("task_document_statistics")
        )

    # ------------------------------------------------------------------
    # Строки задач для расчёта рейтинга
    # ------------------------------------------------------------------

    @classmethod
    async def get_staff_task_scoring_rows(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
            month_plan_id: int | None = None,
            direction_id: int | None = None,
    ):
        """
        Возвращает одну строку на одну задачу
        одного сотрудника.

        Для каждой строки возвращает:

        - сотрудника;
        - роль сотрудника в задаче;
        - статус выполнения;
        - наличие итогового документа;
        - количество назначенных отчётов;
        - количество выполненных отчётов;
        - количество ожидающих отчётов;
        - количество освобождённых отчётов.
        """

        participants = cls._task_participants_subquery()

        final_documents = (
            cls._task_final_document_subquery()
        )

        report_assignments = (
            cls._staff_report_assignment_statistics_subquery()
        )

        conditions = [
            SchoolMonthPlan.school_plan_id
            == school_plan_id,

            SchoolMonthPlanItem.is_included.is_(True),
        ]

        if month_plan_id is not None:
            conditions.append(
                SchoolMonthPlanItem.month_plan_id
                == month_plan_id
            )

        if direction_id is not None:
            conditions.append(
                SchoolPlanRow11.direction_id
                == direction_id
            )

        stmt = (
            select(
                # ------------------------------------------------------
                # Сотрудник
                # ------------------------------------------------------
                User.id.label("user_id"),

                SchoolStaffMember.id.label(
                    "staff_member_id"
                ),

                SchoolStaffMember.full_name.label(
                    "full_name"
                ),

                SchoolStaffMember.position_text.label(
                    "position_text"
                ),

                # ------------------------------------------------------
                # Задача
                # ------------------------------------------------------
                SchoolMonthPlanItem.id.label(
                    "month_item_id"
                ),

                SchoolMonthPlanItem.month_plan_id.label(
                    "month_plan_id"
                ),

                SchoolMonthPlanItem.source_row11_id.label(
                    "source_row11_id"
                ),

                SchoolMonthPlanItem.status.label(
                    "task_status"
                ),

                SchoolMonthPlan.year.label("year"),
                SchoolMonthPlan.month.label("month"),

                SchoolPlanRow11.direction_id.label(
                    "direction_id"
                ),

                # ------------------------------------------------------
                # Роль сотрудника
                # ------------------------------------------------------
                participants.c.assignment_kind.label(
                    "assignment_kind"
                ),

                # ------------------------------------------------------
                # Выполнение
                # ------------------------------------------------------
                case(
                    (
                        SchoolMonthPlanItem.status
                        == PlanItemStatus.DONE,
                        True,
                    ),
                    else_=False,
                ).label("is_completed"),

                # ------------------------------------------------------
                # Итоговый документ задачи
                # ------------------------------------------------------
                func.coalesce(
                    final_documents.c.has_final_document,
                    0,
                ).label("has_final_document"),

                # ------------------------------------------------------
                # Персональные назначения отчётов сотрудника
                # ------------------------------------------------------
                func.coalesce(
                    report_assignments.c.assigned_report_count,
                    0,
                ).label(
                    "assigned_report_count"
                ),

                func.coalesce(
                    report_assignments.c.completed_report_count,
                    0,
                ).label(
                    "completed_report_count"
                ),

                func.coalesce(
                    report_assignments.c.pending_report_count,
                    0,
                ).label(
                    "pending_report_count"
                ),

                func.coalesce(
                    report_assignments.c.waived_report_count,
                    0,
                ).label(
                    "waived_report_count"
                ),
            )
            .select_from(participants)

            # Сотрудник обязателен.
            .join(
                SchoolStaffMember,
                SchoolStaffMember.id
                == participants.c.staff_member_id,
            )

            # Учётная запись может отсутствовать.
            .outerjoin(
                User,
                User.staff_member_id
                == SchoolStaffMember.id,
            )

            .join(
                SchoolMonthPlanItem,
                SchoolMonthPlanItem.id
                == participants.c.month_item_id,
            )

            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )

            .outerjoin(
                SchoolPlanRow11,
                SchoolPlanRow11.id
                == SchoolMonthPlanItem.source_row11_id,
            )

            .outerjoin(
                final_documents,
                final_documents.c.month_item_id
                == SchoolMonthPlanItem.id,
            )

            # Персональные назначения отчётов присоединяются
            # одновременно по задаче и конкретному сотруднику.
            .outerjoin(
                report_assignments,
                (
                    report_assignments.c.month_item_id
                    == SchoolMonthPlanItem.id
                )
                &
                (
                    report_assignments.c.staff_member_id
                    == SchoolStaffMember.id
                ),
            )

            .where(
                *conditions,
            )

            .order_by(
                SchoolStaffMember.full_name.asc(),
                SchoolMonthPlan.year.asc(),
                SchoolMonthPlan.month.asc(),
                SchoolMonthPlanItem.id.asc(),
            )
        )

        result = await db.execute(stmt)
        return result.all()
