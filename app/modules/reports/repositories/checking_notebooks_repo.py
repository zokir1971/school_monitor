# app/modules/reports/repositories/checking_notebooks_repo.py

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.org.models import School
from app.modules.reports.models_documents import TaskExecutionDocument, TaskExecutionSelectedReport
from app.modules.reports.models_template_reports import CheckingNotebooksReport
from app.modules.reports.schemas.checking_notebooks_dto import CheckingNotebooksDTO
from app.modules.staff.models_staff_school import SchoolStaffRole


class CheckingNotebooksRepo:

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
    async def get_by_document_id(
            db: AsyncSession,
            *,
            document_id: int,
    ) -> CheckingNotebooksReport | None:
        result = await db.execute(
            select(CheckingNotebooksReport)
            .where(CheckingNotebooksReport.task_execution_document_id == document_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(
            db: AsyncSession,
            report_id: int,
    ) -> CheckingNotebooksReport | None:
        result = await db.execute(
            select(CheckingNotebooksReport)
            .where(CheckingNotebooksReport.id == report_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_document_and_user(
            db: AsyncSession,
            *,
            document_id: int,
            observer_user_id: int,
    ) -> CheckingNotebooksReport | None:
        stmt = select(CheckingNotebooksReport).where(
            CheckingNotebooksReport.task_execution_document_id == document_id,
            CheckingNotebooksReport.observer_user_id == observer_user_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_document_by_id(
            db: AsyncSession,
            document_id: int,
    ) -> TaskExecutionDocument | None:
        stmt = select(TaskExecutionDocument).where(
            TaskExecutionDocument.id == document_id
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def save_from_dto(
            db: AsyncSession,
            *,
            dto: CheckingNotebooksDTO,
    ) -> CheckingNotebooksReport:
        report = await CheckingNotebooksRepo.get_by_document_and_user(
            db,
            document_id=dto.task_execution_document_id,
            observer_user_id=dto.observer_user_id,
        )

        if not report:
            report = CheckingNotebooksReport(
                month_item_id=dto.month_item_id,
                selected_report_id=dto.selected_report_id,
                task_execution_document_id=dto.task_execution_document_id,
                observer_user_id=dto.observer_user_id,
            )
            db.add(report)

        report.month_item_id = dto.month_item_id
        report.selected_report_id = dto.selected_report_id
        report.task_execution_document_id = dto.task_execution_document_id
        report.user_template_id = dto.user_template_id
        report.observer_user_id = dto.observer_user_id

        report.school_name = dto.school_name
        report.checker_name = dto.checker_name
        report.checker_post = dto.checker_post

        report.teacher_name = dto.teacher_name
        report.class_name = dto.class_name
        report.subject_name = dto.subject_name
        report.check_date = dto.check_date

        report.rows_json = dto.rows_json or []

        report.total_score = dto.total_score
        report.max_score = dto.max_score
        report.percent = dto.percent
        report.level = dto.level

        report.conclusion = dto.conclusion
        report.recommendations = dto.recommendations

        await db.flush()
        await db.refresh(report)

        return report

    @staticmethod
    async def get_school_name_by_id(
            db: AsyncSession,
            *,
            school_id: int,
    ) -> str:
        result = await db.execute(
            select(School.name).where(School.id == school_id)
        )
        return result.scalar_one_or_none() or ""

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
        )

        rows = result.all()

        if not rows:
            return ""

        role, role_context = rows[0]

        # приоритет:
        # 1. ручной текст
        # 2. label enum (каз)
        # 3. value enum
        return (
                role_context
                or getattr(role, "label_kz", None)
                or getattr(role, "value", "")
        )

    @staticmethod
    async def upsert_checking_notebooks_report(
            db: AsyncSession,
            *,
            task_execution_document_id: int,
            month_item_id: int,

            rows_json: dict,
            total_score: int,
            max_score: int,
            percent: int,
            level: str,

            school_name: str,
            checker_name: str,
            checker_post: str,

            teacher_name: str,
            class_name: str,
            subject_name: str,

            check_date: datetime | None,

            conclusion: str,
            recommendations: str,
    ) -> CheckingNotebooksReport:

        report = await CheckingNotebooksRepo.get_by_document_id(
            db,
            document_id=task_execution_document_id,
        )

        if not report:
            report = CheckingNotebooksReport(
                task_execution_document_id=task_execution_document_id,
                month_item_id=month_item_id,
            )
            db.add(report)

        report.rows_json = rows_json

        report.total_score = total_score
        report.max_score = max_score
        report.percent = percent
        report.level = level

        report.school_name = school_name
        report.checker_name = checker_name
        report.checker_post = checker_post

        report.teacher_name = teacher_name
        report.class_name = class_name
        report.subject_name = subject_name

        report.check_date = check_date

        report.conclusion = conclusion
        report.recommendations = recommendations

        await db.flush()

        return report
