# app/modules/reports/repositories/checking_notebooks_repo.py

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, and_, cast, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

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
from app.modules.reports.models_template_reports import CheckingNotebooksReport
from app.modules.reports.schemas.checking_notebooks_dto import (
    CheckerInfoDTO,
    CheckingNotebooksDTO,
    CheckingNotebooksFillContextDTO,
    SchoolInfoDTO,
    TeacherInfoDTO,
)
from app.modules.staff.models_staff_school import SchoolStaffRole, SchoolStaffMember
from app.modules.users.models import User


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
    async def get_fill_context(
            db: AsyncSession,
            *,
            month_item_id: int,
            selected_report_id: int,
            school_id: int,
            staff_member_id: int,
    ) -> CheckingNotebooksFillContextDTO | None:
        """
        Получить весь read-context страницы заполнения одним SQL.

        Проверяет одновременно:
        - selected_report существует;
        - selected_report относится к month_item_id;
        - задача относится к school_id;
        - текущему staff_member_id назначен именно этот отчет.

        Также одним запросом получает:
        - тип/название отчета;
        - школу;
        - должность проверяющего;
        - данные выбранного учителя;
        - текущий рабочий TaskExecutionDocument, если уже создан;
        - CheckingNotebooksReport для этого документа, если уже сохранен.

        Метод ничего не создает и ничего не записывает в БД.
        """

        teacher = aliased(
            SchoolStaffMember,
            name="checking_notebooks_teacher",
        )

        # Последний рабочий документ выбранного отчета.
        # Коррелированный scalar-subquery позволяет не выполнять
        # отдельный SELECT и не размножает строки основного запроса.
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

        checker_role = (
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

        checker_role_context = (
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
                CheckingNotebooksReport,

                ReportTypeModel.code.label("report_code"),
                ReportTypeModel.name_kz.label("report_label"),

                School.id.label("school_id"),
                School.name.label("school_name"),

                checker_role.label("checker_role"),
                checker_role_context.label("checker_role_context"),

                teacher.full_name.label("teacher_name"),
                teacher.subject.label("teacher_subject"),
            )
            .select_from(TaskExecutionSelectedReport)
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
                CheckingNotebooksReport,
                CheckingNotebooksReport.task_execution_document_id
                == TaskExecutionDocument.id,
            )
            .outerjoin(
                teacher,
                and_(
                    TaskExecutionSelectedReport.target_kind == "teacher",
                    cast(teacher.id, String)
                    == TaskExecutionSelectedReport.target_value,
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

        role = row.checker_role
        role_context = row.checker_role_context

        checker_post = (
                role_context
                or getattr(role, "label_kz", None)
                or getattr(role, "value", "")
                or ""
        )

        return CheckingNotebooksFillContextDTO(
            selected_report=selected_report,

            report_code=str(row.report_code or ""),
            report_label=str(row.report_label or ""),

            school_id=int(row.school_id),
            school_name=str(row.school_name or ""),

            checker_post=str(checker_post),

            teacher_name=str(row.teacher_name or ""),
            teacher_subject=str(row.teacher_subject or ""),

            document=document,
            report=report,
        )

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
    async def get_by_document_ids(
            db: AsyncSession,
            *,
            document_ids: list[int],
    ) -> dict[int, CheckingNotebooksReport]:
        """
        Пакетно получить отчеты проверки тетрадей
        для набора TaskExecutionDocument.

        Возвращает:
            task_execution_document_id -> CheckingNotebooksReport

        Используется на странице списка отчетов задачи,
        чтобы не выполнять отдельный SELECT для каждого документа.
        """

        if not document_ids:
            return {}

        stmt = (
            select(CheckingNotebooksReport)
            .where(
                CheckingNotebooksReport.task_execution_document_id.in_(
                    document_ids
                )
            )
            .order_by(
                CheckingNotebooksReport.task_execution_document_id.asc(),
                CheckingNotebooksReport.id.desc(),
            )
        )

        reports = (
            await db.execute(stmt)
        ).scalars().all()

        result: dict[int, CheckingNotebooksReport] = {}

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
    async def get_school_info_by_month_item_id(
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> SchoolInfoDTO | None:
        result = await db.execute(
            select(
                School.id,
                School.name,
            )
            .select_from(SchoolMonthPlanItem)
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id == SchoolMonthPlanItem.month_plan_id,
            )
            .join(
                SchoolPlan,
                SchoolMonthPlan.school_plan_id == SchoolPlan.id,
            )
            .join(
                School,
                SchoolPlan.school_id == School.id,
            )
            .where(SchoolMonthPlanItem.id == month_item_id)
            .limit(1)
        )

        row = result.one_or_none()
        if row is None:
            return None

        return SchoolInfoDTO(
            id=row.id,
            name=row.name,
        )

    @staticmethod
    async def get_checker_info(
            db: AsyncSession,
            *,
            user_id: int,
            school_id: int,
    ) -> CheckerInfoDTO | None:
        result = await db.execute(
            select(
                SchoolStaffMember.full_name,
                SchoolStaffRole.role,
            )
            .select_from(SchoolStaffRole)
            .join(
                SchoolStaffMember,
                SchoolStaffMember.id == SchoolStaffRole.staff_member_id,
            )
            .join(
                User,
                User.staff_member_id == SchoolStaffMember.id,
            )
            .where(
                User.id == user_id,
                SchoolStaffRole.school_id == school_id,
                SchoolStaffRole.is_active.is_(True),
            )
            .limit(1)
        )

        row = result.one_or_none()
        if row is None:
            return None

        return CheckerInfoDTO(
            full_name=row.full_name,
            post=(
                    getattr(row.role, "label_kz", None)
                    or getattr(row.role, "value", "")
            ),
        )

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
    async def get_teacher_info(
            db: AsyncSession,
            teacher_id: int,
    ) -> TeacherInfoDTO | None:
        result = await db.execute(
            select(
                SchoolStaffMember.full_name,
                SchoolStaffMember.subject,
            )
            .where(SchoolStaffMember.id == teacher_id)
            .where(SchoolStaffMember.is_active.is_(True))
            .limit(1)
        )

        row = result.one_or_none()

        if row is None:
            return None

        return TeacherInfoDTO(
            full_name=row.full_name,
            subject=row.subject,
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
