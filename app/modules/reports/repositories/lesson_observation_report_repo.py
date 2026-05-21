# app/modules/reports/repositories/lesson_observation_report_repo.py
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reports.models_documents import TaskExecutionSelectedReport, TaskExecutionDocument
from app.modules.reports.models_template_reports import LessonObservationReport
from app.modules.staff.models_staff_school import SchoolStaffRole, SchoolStaffMember


class LessonObservationReportRepo:
    @staticmethod
    async def get_by_document_id(
        db: AsyncSession,
        *,
        task_execution_document_id: int,
    ) -> LessonObservationReport | None:
        stmt = (
            select(LessonObservationReport)
            .where(
                LessonObservationReport.task_execution_document_id
                == task_execution_document_id
            )
            .limit(1)
        )

        return await db.scalar(stmt)

    @staticmethod
    async def get_selected_report_by_id(
            db: AsyncSession,
            *,
            selected_report_id: int,
    ) -> TaskExecutionSelectedReport | None:
        result = await db.execute(
            select(TaskExecutionSelectedReport)
            .where(TaskExecutionSelectedReport.id == selected_report_id)
        )
        return result.scalar_one_or_none()

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
                SchoolStaffMember.id == staff_member_id,
                SchoolStaffMember.school_id == school_id,
                SchoolStaffMember.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_staff_role_ids(
            db: AsyncSession,
            *,
            school_id: int,
            staff_member_id: int,
    ) -> list[int]:
        result = await db.execute(
            select(SchoolStaffRole.id)
            .where(
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.staff_member_id == staff_member_id,
                SchoolStaffRole.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_controller_post(
            db: AsyncSession,
            *,
            school_id: int,
            staff_member_id: int,
    ) -> str:
        result = await db.execute(
            select(SchoolStaffRole.role, SchoolStaffRole.role_context)
            .where(
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.staff_member_id == staff_member_id,
                SchoolStaffRole.is_active.is_(True),
            )
            .order_by(SchoolStaffRole.id)
            .limit(1)
        )

        row = result.one_or_none()

        if not row:
            return ""

        role, role_context = row

        return role_context or getattr(role, "label_kz", None) or role.value

    @staticmethod
    async def upsert_lesson_observation_report(
            db: AsyncSession,
            *,
            task_execution_document_id: int,
            month_item_id: int,
            criteria_scores: dict,
            total_score: int,

            teacher_full_name: str,
            teacher_position: str,
            teacher_category: str,
            teacher_subject: str,

            observer_full_name: str,
            observer_position: str,

            school_name: str,
            class_name: str,
            group_name: str,

            lesson_datetime: datetime | None,
            theme: str,
            learning_objectives: str,

            lesson_objectives_1: str,
            lesson_objectives_2: str,
            lesson_objectives_3: str,

            feedback: str,
            suggestion_control: str,
    ) -> LessonObservationReport:

        report = await LessonObservationReportRepo.get_by_document_id(
            db,
            task_execution_document_id=task_execution_document_id,
        )

        if not report:
            report = LessonObservationReport(
                task_execution_document_id=task_execution_document_id,
                month_item_id=month_item_id,
            )
            db.add(report)

        report.criteria_scores = criteria_scores
        report.total = total_score

        report.teacher_full_name = teacher_full_name
        report.teacher_position = teacher_position
        report.teacher_category = teacher_category
        report.teacher_subject = teacher_subject

        report.observer_full_name = observer_full_name
        report.observer_position = observer_position

        report.school_name = school_name
        report.class_name = class_name
        report.group_name = group_name

        report.lesson_datetime = lesson_datetime
        report.theme = theme
        report.learning_objectives = learning_objectives

        report.lesson_objectives_1 = lesson_objectives_1
        report.lesson_objectives_2 = lesson_objectives_2
        report.lesson_objectives_3 = lesson_objectives_3

        report.feedback = feedback
        report.suggestion_control = suggestion_control

        await db.flush()

        return report


class LessonObservationRepo:

    @staticmethod
    async def get_by_document_id(
        db: AsyncSession,
        task_execution_document_id: int,
    ) -> LessonObservationReport | None:
        result = await db.execute(
            select(LessonObservationReport)
            .where(
                LessonObservationReport.task_execution_document_id
                == task_execution_document_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        report_id: int,
    ) -> LessonObservationReport | None:
        result = await db.execute(
            select(LessonObservationReport)
            .where(LessonObservationReport.id == report_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def save_from_dto(
        db: AsyncSession,
        *,
        dto,
    ) -> LessonObservationReport:
        report = await LessonObservationRepo.get_by_document_id(
            db,
            dto.task_execution_document_id,
        )

        if report and report.submitted_at is not None:
            raise ValueError("Отчет уже подписан. Редактирование запрещено.")

        if report is None:
            report = LessonObservationReport(
                month_item_id=dto.month_item_id,
                task_execution_document_id=dto.task_execution_document_id,
            )
            db.add(report)

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
        report.lesson_objectives_1 = dto.lesson_objectives_1
        report.lesson_objectives_2 = dto.lesson_objectives_2
        report.lesson_objectives_3 = dto.lesson_objectives_3

        report.criteria_scores = dto.criteria_scores
        report.col_sum_0 = dto.col_sum_0
        report.col_sum_1 = dto.col_sum_1
        report.col_sum_2 = dto.col_sum_2
        report.col_sum_3 = dto.col_sum_3
        report.total = dto.total

        report.suggestion_control = dto.suggestion_control
        report.feedback = dto.feedback

        await db.flush()
        return report

    @staticmethod
    async def get_document_by_id(
            db: AsyncSession,
            document_id: int,
    ) -> TaskExecutionDocument | None:
        result = await db.execute(
            select(TaskExecutionDocument)
            .where(TaskExecutionDocument.id == document_id)
        )
        return result.scalar_one_or_none()
