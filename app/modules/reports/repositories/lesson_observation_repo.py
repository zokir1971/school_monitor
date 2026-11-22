# app/modules/reports/repositories/lesson_observation_repo.py
from __future__ import annotations

from sqlalchemy import String, and_, cast, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload, aliased, selectinload

from app.modules.org.models import School
from app.modules.planning.models_month_plan import SchoolMonthPlan, SchoolMonthPlanItem
from app.modules.planning.models_school import SchoolPlan
from app.modules.reports.models_documents import (
    ReportTypeModel,
    TaskExecutionData,
    TaskExecutionDocument,
    TaskExecutionSelectedReport,
)
from app.modules.reports.models_report_assignments import (
    TaskSelectedReportAssignment,
)
from app.modules.reports.models_template_reports import LessonObservationReport
from app.modules.reports.schemas.lesson_observation_dto import (
    LessonObservationFillContextDTO,
    LessonObservationFormDTO,
)
from app.modules.staff.models_staff_school import (
    SchoolStaffMember,
    SchoolStaffRole,
)


class LessonObservationRepo:
    """
    Универсальный repository листа наблюдения урока.

    Используется и пользовательским, и системным сценарием.

    Repository отвечает только за работу с БД:
    - выбранный отчет;
    - сущность LessonObservationReport;
    - данные сотрудников;
    - создание/обновление отчета.

    TaskExecutionDocument здесь не создается:
    это ответственность ExecutionDocumentRepo.
    """

    # =========================================================
    # SELECTED REPORT
    # =========================================================

    @staticmethod
    async def get_selected_report_by_id(
            db: AsyncSession,
            *,
            selected_report_id: int,
    ) -> TaskExecutionSelectedReport | None:
        """
        Получить выбранный отчет вместе с типом отчета.

        report_type загружается явно,
        потому что в модели используется lazy="raise".
        """

        stmt = (
            select(TaskExecutionSelectedReport).options(raiseload("*"))
            .where(
                TaskExecutionSelectedReport.id
                == selected_report_id
            )
            .options(
                selectinload(
                    TaskExecutionSelectedReport.report_type
                ),
                selectinload(
                    TaskExecutionSelectedReport.execution_data
                ),
            )
            .limit(1)
        )

        return await db.scalar(stmt)

    # =========================================================
    # FILL CONTEXT
    # =========================================================

    @staticmethod
    async def get_fill_context(
            db: AsyncSession,
            *,
            month_item_id: int,
            selected_report_id: int,
            school_id: int,
            staff_member_id: int,
    ) -> LessonObservationFillContextDTO | None:
        """
        Получить весь read-context страницы листа наблюдения одним SQL.

        Одновременно проверяет:
        - selected_report существует;
        - selected_report относится к month_item_id;
        - задача относится к school_id;
        - текущему staff_member_id назначен именно этот отчет.

        Одним запросом получает:
        - тип и название отчета;
        - школу;
        - должность наблюдателя;
        - выбранного педагога и его данные;
        - текущий рабочий TaskExecutionDocument, если он уже существует;
        - LessonObservationReport для документа, если уже сохранен.

        Метод является read-only и ничего не создает в БД.
        """

        teacher = aliased(
            SchoolStaffMember,
            name="lesson_observation_teacher",
        )

        # Последний рабочий документ конкретного selected_report.
        # Это позволяет не делать отдельный запрос документа.
        latest_document_id = (
            select(TaskExecutionDocument.id)
            .where(
                TaskExecutionDocument.selected_report_id
                == TaskExecutionSelectedReport.id,
                TaskExecutionDocument.is_final.is_(False),
            )
            .order_by(
                TaskExecutionDocument.is_current.desc(),
                TaskExecutionDocument.id.desc(),
            )
            .limit(1)
            .correlate(TaskExecutionSelectedReport)
            .scalar_subquery()
        )

        # Должность наблюдателя получаем scalar-subquery,
        # чтобы не размножать строки основного SELECT при наличии
        # нескольких активных ролей сотрудника.
        observer_role = (
            select(SchoolStaffRole.role)
            .where(
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.staff_member_id == staff_member_id,
                SchoolStaffRole.is_active.is_(True),
            )
            .order_by(SchoolStaffRole.id.asc())
            .limit(1)
            .scalar_subquery()
        )

        observer_role_context = (
            select(SchoolStaffRole.role_context)
            .where(
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.staff_member_id == staff_member_id,
                SchoolStaffRole.is_active.is_(True),
            )
            .order_by(SchoolStaffRole.id.asc())
            .limit(1)
            .scalar_subquery()
        )

        stmt = (
            select(
                TaskExecutionSelectedReport,
                TaskExecutionDocument,
                LessonObservationReport,

                ReportTypeModel.code.label("report_code"),
                ReportTypeModel.name_kz.label("report_label"),

                School.id.label("school_id"),
                School.name.label("school_name"),

                observer_role.label("observer_role"),
                observer_role_context.label(
                    "observer_role_context"
                ),

                teacher.id.label("teacher_staff_id"),
                teacher.full_name.label("teacher_full_name"),
                teacher.position_text.label("teacher_position"),
                teacher.qualification_category.label(
                    "teacher_category"
                ),
                teacher.subject.label("teacher_subject"),
            )
            .options(raiseload("*")).select_from(TaskExecutionSelectedReport)
            .join(
                TaskSelectedReportAssignment,
                TaskSelectedReportAssignment.selected_report_id
                == TaskExecutionSelectedReport.id,
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
            .join(
                School,
                School.id
                == SchoolPlan.school_id,
            )
            .join(
                ReportTypeModel,
                ReportTypeModel.id
                == TaskExecutionSelectedReport.report_type_id,
            )
            .outerjoin(
                TaskExecutionDocument,
                TaskExecutionDocument.id
                == latest_document_id,
            )
            .outerjoin(
                LessonObservationReport,
                LessonObservationReport.task_execution_document_id
                == TaskExecutionDocument.id,
            )
            .outerjoin(
                teacher,
                and_(
                    TaskExecutionSelectedReport.target_kind
                    == "teacher",
                    cast(teacher.id, String)
                    == TaskExecutionSelectedReport.target_value,
                    teacher.school_id == school_id,
                    teacher.is_active.is_(True),
                ),
            )
            .where(
                TaskExecutionSelectedReport.id == selected_report_id,
                TaskExecutionData.month_item_id == month_item_id,
                TaskSelectedReportAssignment.staff_member_id
                == staff_member_id,
                SchoolPlan.school_id == school_id,
                SchoolMonthPlanItem.is_included.is_(True),
            )
            .limit(1)
        )

        row = (
            await db.execute(stmt)
        ).one_or_none()

        if row is None:
            return None

        selected_report = row[0]
        document = row[1]
        report = row[2]

        role = row.observer_role
        role_context = row.observer_role_context

        observer_position = (
                role_context
                or getattr(role, "label_kz", None)
                or getattr(role, "value", "")
                or ""
        )

        teacher_position = str(
            row.teacher_position or ""
        )

        teacher_category = str(
            row.teacher_category or ""
        )

        # Для отображения сохраняем привычное правило:
        # должность + квалификационная категория.
        if (
                teacher_category
                and teacher_category not in teacher_position
        ):
            teacher_position = (
                f"{teacher_position}, {teacher_category}"
                if teacher_position
                else teacher_category
            )

        teacher_staff_id = (
            int(row.teacher_staff_id)
            if row.teacher_staff_id is not None
            else None
        )

        return LessonObservationFillContextDTO(
            selected_report=selected_report,

            report_code=str(row.report_code or ""),
            report_label=str(row.report_label or ""),

            school_id=int(row.school_id),
            school_name=str(row.school_name or ""),

            observer_position=str(observer_position),

            teacher_staff_id=teacher_staff_id,
            teacher_full_name=str(
                row.teacher_full_name
                or selected_report.target_label
                or ""
            ),
            teacher_position=teacher_position,
            teacher_category=teacher_category,
            teacher_subject=str(row.teacher_subject or ""),

            document=document,
            report=report,
        )

    # =========================================================
    # REPORT
    # =========================================================

    @staticmethod
    async def get_by_document_id(
            db: AsyncSession,
            *,
            document_id: int,
    ) -> LessonObservationReport | None:
        result = await db.execute(
            select(LessonObservationReport).options(raiseload("*"))
            .where(
                LessonObservationReport.task_execution_document_id
                == document_id
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_document_ids(
            db: AsyncSession,
            *,
            document_ids: list[int],
    ) -> dict[int, LessonObservationReport]:
        """
        Пакетно получить листы наблюдения урока
        для набора TaskExecutionDocument.

        Возвращает:
            task_execution_document_id -> LessonObservationReport

        Используется на странице списка отчетов задачи,
        чтобы не выполнять отдельный SELECT для каждого документа.
        """

        if not document_ids:
            return {}

        stmt = (
            select(LessonObservationReport).options(raiseload("*"))
            .where(
                LessonObservationReport.task_execution_document_id.in_(
                    document_ids
                )
            )
            .order_by(
                LessonObservationReport.task_execution_document_id.asc(),
                LessonObservationReport.id.desc(),
            )
        )

        reports = (
            await db.execute(stmt)
        ).scalars().all()

        result: dict[int, LessonObservationReport] = {}

        for report in reports:
            document_id = report.task_execution_document_id

            if document_id is None:
                continue

            document_id = int(document_id)

            if document_id not in result:
                result[document_id] = report

        return result

    @staticmethod
    async def get_by_id(
            db: AsyncSession,
            report_id: int,
    ) -> LessonObservationReport | None:
        result = await db.execute(
            select(LessonObservationReport).options(raiseload("*"))
            .where(
                LessonObservationReport.id
                == report_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_document_and_user(
            db: AsyncSession,
            *,
            document_id: int,
            observer_user_id: int,
    ) -> LessonObservationReport | None:
        result = await db.execute(
            select(LessonObservationReport).options(raiseload("*"))
            .where(
                LessonObservationReport.task_execution_document_id
                == document_id,
                LessonObservationReport.observer_user_id
                == observer_user_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    # =========================================================
    # SCHOOL / MONTH ITEM CONTEXT
    # =========================================================

    @staticmethod
    async def get_school_name_by_month_item_id(
            db: AsyncSession,
            *,
            month_item_id: int,
            school_id: int,
    ) -> str | None:
        """
        Получить название школы для конкретной задачи месячного плана.

        school_id является границей доступа: метод вернет None,
        если задача существует, но относится к другой школе.

        Цепочка:
            SchoolMonthPlanItem
                -> SchoolMonthPlan
                    -> SchoolPlan
                        -> School
        """

        stmt = (
            select(School.name)
            .select_from(SchoolMonthPlanItem)
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id == SchoolMonthPlanItem.month_plan_id,
            )
            .join(
                SchoolPlan,
                SchoolPlan.id == SchoolMonthPlan.school_plan_id,
            )
            .join(
                School,
                School.id == SchoolPlan.school_id,
            )
            .where(
                SchoolMonthPlanItem.id == month_item_id,
                School.id == school_id,
            )
            .limit(1)
        )

        return await db.scalar(stmt)

    # =========================================================
    # STAFF
    # =========================================================

    @staticmethod
    async def get_staff_member_by_id(
            db: AsyncSession,
            *,
            school_id: int,
            staff_member_id: int,
    ) -> SchoolStaffMember | None:
        result = await db.execute(
            select(SchoolStaffMember)
            .where(
                SchoolStaffMember.id
                == staff_member_id,
                SchoolStaffMember.school_id
                == school_id,
                SchoolStaffMember.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_teacher_info(
            db: AsyncSession,
            *,
            teacher_id: int,
    ) -> SchoolStaffMember | None:
        """
        Данные педагога для автозаполнения системного шаблона.

        Возвращаем SchoolStaffMember, поскольку сервису нужны:
        full_name, subject, position_text,
        qualification_category.
        """
        result = await db.execute(
            select(SchoolStaffMember)
            .where(
                SchoolStaffMember.id == teacher_id,
                SchoolStaffMember.is_active.is_(True),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_controller_post(
            db: AsyncSession,
            *,
            school_id: int,
            staff_member_id: int,
    ) -> str:
        result = await db.execute(
            select(
                SchoolStaffRole.role,
                SchoolStaffRole.role_context,
            )
            .where(
                SchoolStaffRole.school_id
                == school_id,
                SchoolStaffRole.staff_member_id
                == staff_member_id,
                SchoolStaffRole.is_active.is_(True),
            )
            .order_by(SchoolStaffRole.id)
            .limit(1)
        )

        row = result.one_or_none()

        if row is None:
            return ""

        role, role_context = row

        return (
                role_context
                or getattr(role, "label_kz", None)
                or getattr(role, "value", "")
        )

    # =========================================================
    # SAVE FROM DTO
    # =========================================================

    @classmethod
    async def save_from_dto(
            cls,
            db: AsyncSession,
            *,
            dto: LessonObservationFormDTO,
    ) -> LessonObservationReport:
        """
        Создать или обновить лист наблюдения из DTO.

        Используется пользовательским сценарием.
        Может использоваться и системным сценарием,
        если он будет переведен на LessonObservationFormDTO.
        """

        if dto.observer_user_id is not None:
            report = await cls.get_by_document_and_user(
                db,
                document_id=dto.task_execution_document_id,
                observer_user_id=dto.observer_user_id,
            )
        else:
            report = await cls.get_by_document_id(
                db,
                document_id=dto.task_execution_document_id,
            )

        if (
                report is not None
                and report.submitted_at is not None
        ):
            raise ValueError(
                "Отчет уже подписан. "
                "Редактирование запрещено."
            )

        if report is None:
            report = LessonObservationReport(
                month_item_id=dto.month_item_id,
                task_execution_document_id=(
                    dto.task_execution_document_id
                ),
                observer_user_id=dto.observer_user_id,
            )
            db.add(report)

        report.month_item_id = dto.month_item_id
        report.task_execution_document_id = (
            dto.task_execution_document_id
        )

        report.staff_member_id = dto.staff_member_id
        report.observer_user_id = dto.observer_user_id

        report.teacher_full_name = dto.teacher_full_name
        report.teacher_position = dto.teacher_position
        report.teacher_category = dto.teacher_category
        report.teacher_subject = dto.teacher_subject

        report.observer_full_name = dto.observer_full_name
        report.observer_position = dto.observer_position

        report.school_name = dto.school_name
        report.class_name = dto.class_name
        report.group_name = dto.group_name

        report.lesson_datetime = dto.lesson_datetime
        report.theme = dto.theme
        report.learning_objectives = dto.learning_objectives

        report.lesson_objectives_1 = (
            dto.lesson_objectives_1
        )
        report.lesson_objectives_2 = (
            dto.lesson_objectives_2
        )
        report.lesson_objectives_3 = (
            dto.lesson_objectives_3
        )

        report.criteria_scores = (
                dto.criteria_scores or {}
        )

        report.col_sum_0 = dto.col_sum_0
        report.col_sum_1 = dto.col_sum_1
        report.col_sum_2 = dto.col_sum_2
        report.col_sum_3 = dto.col_sum_3
        report.total = dto.total

        report.suggestion_control = (
            dto.suggestion_control
        )
        report.feedback = dto.feedback

        await db.flush()
        await db.refresh(report, attribute_names=list(type(report).__mapper__.column_attrs.keys()))

        return report
