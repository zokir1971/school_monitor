# app/modules/reports/repositories/system_lesson_observation_repo.py

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.reports.enums import (
    DocumentType,
    TaskDocumentStatus,
    TaskDocumentSource,
)

from app.modules.reports.models_documents import (
    TaskExecutionDocument,
    TaskExecutionSelectedReport,
)

from app.modules.reports.models_template_reports import (
    LessonObservationReport,
)
from app.modules.reports.system_report_dto.system_lesson_observation_dto import TeacherInfoDTO

from app.modules.staff.models_staff_school import (
    SchoolStaffMember,
    SchoolStaffRole,
)


class SystemLessonObservationRepo:
    # =========================================================
    # SELECTED REPORT
    # =========================================================

    @staticmethod
    async def get_selected_report(
        db: AsyncSession,
        *,
        selected_report_id: int,
    ) -> TaskExecutionSelectedReport | None:
        stmt = (
            select(TaskExecutionSelectedReport)
            .options(
                selectinload(TaskExecutionSelectedReport.report_type),
            )
            .where(TaskExecutionSelectedReport.id == selected_report_id)
            .limit(1)
        )

        return await db.scalar(stmt)

    # =========================================================
    # STAFF / DEFAULT INFO
    # =========================================================

    @staticmethod
    async def get_staff_member_by_id(
        db: AsyncSession,
        *,
        school_id: int,
        staff_member_id: int,
    ) -> SchoolStaffMember | None:
        stmt = (
            select(SchoolStaffMember)
            .where(
                SchoolStaffMember.id == staff_member_id,
                SchoolStaffMember.school_id == school_id,
                SchoolStaffMember.is_active.is_(True),
            )
            .limit(1)
        )

        return await db.scalar(stmt)

    @staticmethod
    async def get_staff_member_with_first_role(
        db: AsyncSession,
        *,
        school_id: int,
        staff_member_id: int,
    ) -> tuple[SchoolStaffMember | None, str]:
        stmt = (
            select(
                SchoolStaffMember,
                SchoolStaffRole.role,
                SchoolStaffRole.role_context,
            )
            .outerjoin(
                SchoolStaffRole,
                and_(
                    SchoolStaffRole.school_id == SchoolStaffMember.school_id,
                    SchoolStaffRole.staff_member_id == SchoolStaffMember.id,
                    SchoolStaffRole.is_active.is_(True),
                ),
            )
            .where(
                SchoolStaffMember.id == staff_member_id,
                SchoolStaffMember.school_id == school_id,
                SchoolStaffMember.is_active.is_(True),
            )
            .order_by(SchoolStaffRole.id.asc())
            .limit(1)
        )

        result = await db.execute(stmt)
        row = result.one_or_none()

        if not row:
            return None, ""

        staff_member, role, role_context = row

        position = (
            role_context
            or getattr(role, "label_kz", None)
            or getattr(role, "value", None)
            or ""
        )

        return staff_member, position

    @staticmethod
    async def get_controller_post(
        db: AsyncSession,
        *,
        school_id: int,
        staff_member_id: int,
    ) -> str:
        stmt = (
            select(
                SchoolStaffRole.role,
                SchoolStaffRole.role_context,
            )
            .where(
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.staff_member_id == staff_member_id,
                SchoolStaffRole.is_active.is_(True),
            )
            .order_by(SchoolStaffRole.id.asc())
            .limit(1)
        )

        result = await db.execute(stmt)
        row = result.one_or_none()

        if not row:
            return ""

        role, role_context = row

        return (
            role_context
            or getattr(role, "label_kz", None)
            or getattr(role, "value", None)
            or ""
        )

    @staticmethod
    async def get_teacher_info(
            db: AsyncSession,
            teacher_id: int,
    ) -> TeacherInfoDTO | None:
        result = await db.execute(
            select(
                SchoolStaffMember.full_name,
                SchoolStaffMember.subject,
                SchoolStaffMember.position_text,
                SchoolStaffMember.qualification_category,
            )
            .where(
                SchoolStaffMember.id == teacher_id,
                SchoolStaffMember.is_active.is_(True),
            )
            .limit(1)
        )

        row = result.one_or_none()

        if row is None:
            return None

        return TeacherInfoDTO(
            full_name=row.full_name,
            subject=row.subject,
            position_text=row.position_text,
            qualification_category=row.qualification_category,
        )

    # =========================================================
    # DOCUMENT
    # =========================================================

    @staticmethod
    async def get_current_document(
        db: AsyncSession,
        *,
        month_item_id: int,
        selected_report_id: int,
        user_id: int,
    ) -> TaskExecutionDocument | None:
        stmt = (
            select(TaskExecutionDocument)
            .where(
                TaskExecutionDocument.month_item_id == month_item_id,
                TaskExecutionDocument.selected_report_id == selected_report_id,
                TaskExecutionDocument.uploaded_by_user_id == user_id,
                TaskExecutionDocument.source == TaskDocumentSource.GENERATED,
                TaskExecutionDocument.is_current.is_(True),
                TaskExecutionDocument.is_final.is_(False),
            )
            .limit(1)
        )

        return await db.scalar(stmt)

    @staticmethod
    async def create_document(
        db: AsyncSession,
        *,
        month_item_id: int,
        selected_report_id: int,
        user_id: int,
        report_code: str,
        report_label: str,
        schema_json: dict,
    ) -> TaskExecutionDocument:
        document = TaskExecutionDocument(
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            uploaded_by_user_id=user_id,

            report_code=report_code,
            report_label=report_label,

            document_type=DocumentType.REPORT,
            status=TaskDocumentStatus.DRAFT,
            source=TaskDocumentSource.GENERATED,

            is_current=True,
            is_final=False,
            version=1,

            schema_json=schema_json or {},
        )

        db.add(document)

        await db.flush()
        await db.refresh(document)

        return document

    @classmethod
    async def get_or_create_document(
        cls,
        db: AsyncSession,
        *,
        month_item_id: int,
        selected_report_id: int,
        user_id: int,
        report_code: str,
        report_label: str = "Системный отчет",
        schema_json: dict,
    ) -> TaskExecutionDocument:
        document = await cls.get_current_document(
            db,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            user_id=user_id,
        )

        if document:
            if not document.schema_json:
                document.schema_json = schema_json or {}
                db.add(document)
                await db.flush()

            return document

        return await cls.create_document(
            db,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            user_id=user_id,
            report_code=report_code,
            report_label=report_label,
            schema_json=schema_json,
        )

    # =========================================================
    # LESSON OBSERVATION REPORT
    # =========================================================

    @staticmethod
    async def get_lesson_observation_report(
        db: AsyncSession,
        *,
        document_id: int,
    ) -> LessonObservationReport | None:
        stmt = (
            select(LessonObservationReport)
            .where(
                LessonObservationReport.task_execution_document_id == document_id,
            )
            .limit(1)
        )

        return await db.scalar(stmt)

    @staticmethod
    async def create_lesson_observation_report(
        db: AsyncSession,
        *,
        month_item_id: int,
        document_id: int,
        observer_user_id: int | None = None,
    ) -> LessonObservationReport:
        report = LessonObservationReport(
            month_item_id=month_item_id,
            task_execution_document_id=document_id,
            observer_user_id=observer_user_id,
            criteria_scores={},
        )

        db.add(report)

        await db.flush()
        await db.refresh(report)

        return report

    @classmethod
    async def get_or_create_lesson_observation_report(
        cls,
        db: AsyncSession,
        *,
        month_item_id: int,
        document_id: int,
        observer_user_id: int | None = None,
    ) -> LessonObservationReport:
        report = await cls.get_lesson_observation_report(
            db,
            document_id=document_id,
        )

        if report:
            return report

        return await cls.create_lesson_observation_report(
            db,
            month_item_id=month_item_id,
            document_id=document_id,
            observer_user_id=observer_user_id,
        )

    # =========================================================
    # SAVE
    # =========================================================

    @staticmethod
    async def save_lesson_observation_report(
            db: AsyncSession,
            report: LessonObservationReport,
            *,
            document: TaskExecutionDocument | None = None,
            schema_json: dict | None = None,
    ) -> LessonObservationReport:

        criteria_scores = report.criteria_scores or {}
        col_sums = criteria_scores.get("col_sums") or {}

        report.col_sum_0 = int(col_sums.get("0") or 0)
        report.col_sum_1 = int(col_sums.get("1") or 0)
        report.col_sum_2 = int(col_sums.get("2") or 0)
        report.col_sum_3 = int(col_sums.get("3") or 0)

        report.total = int(criteria_scores.get("total_score") or report.total or 0)

        db.add(report)

        if document is not None:
            if schema_json is not None:
                document.schema_json = schema_json

            document.title = document.title or "Лист наблюдения урока"
            db.add(document)

        await db.flush()
        return report
