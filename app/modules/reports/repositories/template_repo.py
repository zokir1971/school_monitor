from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.planning.models_month_plan import SchoolMonthPlan, SchoolMonthPlanItem, SchoolMonthPlanItemAssignee, \
    SchoolMonthPlanItemReviewPlace
from app.modules.planning.models_school import SchoolPlan
from app.modules.reports.enums import (
    DocumentType,
    TaskDocumentSource,
    TaskDocumentStatus, ReportTemplateMode, )
from app.modules.reports.models_documents import (
    TaskExecutionDocument,
    TaskExecutionSelectedReport, TaskExecutionData,
)
from app.modules.reports.models_template_reports import LessonObservationReport, UserReportTemplate
from app.modules.staff.models_staff_school import SchoolStaffRole, SchoolStaffMember
from app.modules.users.models import User


class TemplateReportRepo:
    """
    Репозиторий системных шаблонов отчетов.

    ВАЖНО:
    Теперь основной ключ логики — selected_report_id.
    Это убирает проблему дублирования report_code.
    """

    @staticmethod
    def _apply_executor_user_filter(stmt, *, user_id: int):
        """
        Ограничить запрос задачами, где текущий пользователь является исполнителем.

        Повторяет логику ReportRepo, но находится внутри TemplateReportRepo,
        чтобы не обращаться к protected-методу другого класса.
        """

        return stmt.where(
            SchoolMonthPlanItem.assignees.any(
                SchoolMonthPlanItemAssignee.staff_role.has(
                    SchoolStaffRole.staff_member.has(
                        SchoolStaffMember.user_account.has(User.id == user_id)
                    )
                )
            )
        )

    @classmethod
    async def get_task_for_templates_page(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
    ) -> SchoolMonthPlanItem | None:
        """
        Получить задачу для страницы подготовки системных отчетов.

        Проверяет доступ:
        - принадлежность к школе
        - назначение исполнителем
        """

        stmt = (
            select(SchoolMonthPlanItem)
            .where(
                SchoolMonthPlanItem.id == month_item_id,
                SchoolMonthPlanItem.assignees.any(
                    SchoolMonthPlanItemAssignee.staff_role.has(
                        SchoolStaffRole.staff_member.has(
                            SchoolStaffMember.user_account.has(
                                User.id == user_id
                            )
                        )
                    )
                )
            )
            .options(
                selectinload(SchoolMonthPlanItem.assignees)
                .selectinload(SchoolMonthPlanItemAssignee.staff_role)
                .selectinload(SchoolStaffRole.staff_member)
                .selectinload(SchoolStaffMember.user_account),

                selectinload(SchoolMonthPlanItem.source_row11),

                selectinload(SchoolMonthPlanItem.month_plan)
                .selectinload(SchoolMonthPlan.school_plan)
                .selectinload(SchoolPlan.school),
            )
        )
        return await db.scalar(stmt)

    @classmethod
    async def get_execution_data_for_templates(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> TaskExecutionData | None:
        """
        Получить execution_data вместе с выбранными отчетами.

        Нужен для промежуточной страницы:
        - какие отчеты выбрал исполнитель;
        - для какого объекта/учителя/класса каждый отчет.
        """

        stmt = (
            select(TaskExecutionData)
            .where(TaskExecutionData.month_item_id == month_item_id)
            .options(
                selectinload(TaskExecutionData.selected_reports).selectinload(
                    TaskExecutionSelectedReport.report_type
                )
            )
        )

        return await db.scalar(stmt)

    # =========================
    # SELECTED REPORT
    # =========================

    @classmethod
    async def get_selected_report(
            cls,
            db: AsyncSession,
            *,
            selected_report_id: int,
    ) -> TaskExecutionSelectedReport | None:
        """
        Получить выбранный отчет исполнителя.

        Используется:
        - при открытии формы шаблона
        - для получения report_type
        """
        stmt = (
            select(TaskExecutionSelectedReport)
            .where(TaskExecutionSelectedReport.id == selected_report_id)
            .options(selectinload(TaskExecutionSelectedReport.report_type))
        )

        return await db.scalar(stmt)

    # =========================
    # DOCUMENT
    # =========================
    @classmethod
    async def get_template_document(
            cls,
            db: AsyncSession,
            *,
            selected_report_id: int,
            user_id: int,
    ) -> TaskExecutionDocument | None:
        """
        Получить текущий документ шаблонного отчета
        """
        stmt = (
            select(TaskExecutionDocument)
            .where(
                TaskExecutionDocument.selected_report_id == selected_report_id,
                TaskExecutionDocument.is_final.is_(False),
            )
            .order_by(TaskExecutionDocument.is_current.desc(), TaskExecutionDocument.id.desc())
            .limit(1)
        )

        return await db.scalar(stmt)

    @classmethod
    async def create_or_update_template_document(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
            selected_report: TaskExecutionSelectedReport,
    ) -> TaskExecutionDocument:
        """
        Создать или обновить TaskExecutionDocument для шаблона.

        Логика:
        - если есть текущий → обновляем
        - если нет → создаем

        selected_report:
            содержит report_type, target и т.д.
        """

        existing = await cls.get_template_document(
            db,
            selected_report_id=selected_report.id,
            user_id=user_id,
        )

        report_type = selected_report.report_type

        if existing:
            existing.report_type_id = report_type.id if report_type else None
            existing.report_code = report_type.code if report_type else None
            existing.report_label = (
                report_type.name_kz if report_type else None
            )
            existing.title = report_type.name_kz if report_type else None

            existing.status = TaskDocumentStatus.DRAFT
            existing.source = TaskDocumentSource.GENERATED
            existing.is_current = True
            existing.is_final = False

            await db.flush()
            return existing

        document = TaskExecutionDocument(
            month_item_id=month_item_id,
            selected_report_id=selected_report.id,

            report_type_id=report_type.id if report_type else None,
            report_code=report_type.code if report_type else None,
            report_label=report_type.name_kz if report_type else None,

            document_type=DocumentType.REPORT,
            status=TaskDocumentStatus.DRAFT,
            source=TaskDocumentSource.GENERATED,

            version=1,
            is_current=True,
            is_final=False,
            title=report_type.name_kz if report_type else None,
        )

        db.add(document)
        await db.flush()
        return document

    @classmethod
    async def get_review_places_for_month_item(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> list[str]:

        stmt = (
            select(SchoolMonthPlanItemReviewPlace.review_place)
            .where(
                SchoolMonthPlanItemReviewPlace.month_item_id == month_item_id
            )
        )

        result = await db.execute(stmt)

        return list(result.scalars().all())

    # =========================
    # LESSON OBSERVATION
    # =========================

    @classmethod
    async def get_lesson_observation(
            cls,
            db: AsyncSession,
            *,
            document_id: int,
    ) -> LessonObservationReport | None:
        """
        Получить данные формы "Лист наблюдения урока".

        1 документ → 1 запись LessonObservationReport.
        """
        stmt = (
            select(LessonObservationReport)
            .where(
                LessonObservationReport.task_execution_document_id == document_id
            )
            .options(
                selectinload(LessonObservationReport.staff_member),
                selectinload(LessonObservationReport.observer_user),
            )
        )

        return await db.scalar(stmt)

    @classmethod
    async def upsert_lesson_observation(
            cls,
            db: AsyncSession,
            *,
            document: TaskExecutionDocument,
            data,
    ) -> LessonObservationReport:
        """
        Создать или обновить данные шаблона.

        data = LessonObservationFormDTO

        Логика:
        - если запись есть → обновляем
        - если нет → создаем
        """

        report = await cls.get_lesson_observation(
            db,
            document_id=document.id,
        )

        if not report:
            report = LessonObservationReport(
                month_item_id=data.month_item_id,
                task_execution_document_id=document.id,
            )
            db.add(report)

        # =========================
        # teacher
        # =========================
        report.staff_member_id = data.staff_member_id

        report.teacher_full_name = data.teacher_full_name
        report.teacher_position = data.teacher_position
        report.teacher_category = data.teacher_category
        report.teacher_subject = data.teacher_subject

        # =========================
        # observer
        # =========================
        report.observer_user_id = data.observer_user_id

        report.observer_full_name = data.observer_full_name
        report.observer_position = data.observer_position

        # =========================
        # lesson data
        # =========================
        report.school_name = data.school_name
        report.class_name = data.class_name
        report.group_name = data.group_name

        report.lesson_datetime = data.lesson_datetime

        report.theme = data.theme
        report.learning_objectives = data.learning_objectives

        report.lesson_objectives_1 = data.lesson_objectives_1
        report.lesson_objectives_2 = data.lesson_objectives_2
        report.lesson_objectives_3 = data.lesson_objectives_3

        report.lesson_plan_filename = data.lesson_plan_filename

        # =========================
        # scores
        # =========================
        report.col_sum_0 = data.col_sum_0
        report.col_sum_1 = data.col_sum_1
        report.col_sum_2 = data.col_sum_2
        report.col_sum_3 = data.col_sum_3
        report.total = data.total

        # =========================
        # results
        # =========================
        report.suggestion_control = data.suggestion_control
        report.feedback = data.feedback

        await db.flush()
        return report

    # =========================
    # SUBMIT SYSTEM REPORTS
    # =========================

    @classmethod
    async def mark_system_reports_submitted(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
    ) -> None:
        """
        Перевести ВСЕ системные отчеты задачи в SUBMITTED.

        Используется при:
        completion_mode = FINAL_WITH_SYSTEM_REPORTS

        Делает:
        - только is_final=False
        - только selected_report_id != None
        """

        now = datetime.now(timezone.utc)

        stmt = (
            update(TaskExecutionDocument)
            .where(
                TaskExecutionDocument.month_item_id == month_item_id,
                TaskExecutionDocument.is_current.is_(True),
                TaskExecutionDocument.is_final.is_(False),
                TaskExecutionDocument.selected_report_id.is_not(None),
            )
            .values(
                status=TaskDocumentStatus.SUBMITTED,
                submitted_by_user_id=user_id,
                submitted_at=now,
            )
        )

        await db.execute(stmt)

    @classmethod
    async def apply_custom_template_to_document(
            cls,
            db: AsyncSession,
            *,
            document: TaskExecutionDocument,
            user_template: UserReportTemplate,
    ) -> TaskExecutionDocument:
        """
        Применить личный шаблон к документу конкретной задачи.

        Важно:
        - custom_template_id хранит ссылку на личный шаблон;
        - custom_content_html/text — snapshot-копия;
        - если пользователь потом изменит личный шаблон,
          уже подготовленный отчет по задаче не изменится.
        """

        document.custom_template_id = user_template.id
        document.template_mode = ReportTemplateMode.CUSTOM.value

        document.custom_content_html = user_template.content_html
        document.custom_content_text = user_template.content_text

        # snapshot конструктора шаблона
        document.schema_json = user_template.schema_json

        document.status = TaskDocumentStatus.DRAFT

        await db.flush()
        return document
