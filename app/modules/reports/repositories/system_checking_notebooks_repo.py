from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.org.models import School
from app.modules.planning.models_month_plan import SchoolMonthPlanItem, SchoolMonthPlan
from app.modules.planning.models_school import SchoolPlan
from app.modules.reports.models_documents import TaskExecutionSelectedReport, TaskExecutionDocument
from app.modules.reports.models_template_reports import CheckingNotebooksReport
from app.modules.reports.system_report_dto.system_checking_notebooks_dto import CheckerInfoDTO, TeacherInfoDTO, \
    SchoolInfoDTO
from app.modules.staff.models_staff_school import SchoolStaffRole, SchoolStaffMember
from app.modules.users.models import User


class CheckingNotebooksSystemRepo:
    @staticmethod
    async def create(
            db: AsyncSession,
            *,
            document_id: int,
            selected_report_id: int,
            month_item_id: int,
            created_by_user_id: int,
    ):
        report = CheckingNotebooksReport(
            task_execution_document_id=document_id,
            selected_report_id=selected_report_id,
            month_item_id=month_item_id,
            created_by_user_id=created_by_user_id,
        )

        db.add(report)
        await db.flush()
        await db.refresh(report)

        return report

    @staticmethod
    async def get_selected_report_by_id(
            db: AsyncSession,
            selected_report_id: int,
    ) -> TaskExecutionSelectedReport | None:
        result = await db.execute(
            select(TaskExecutionSelectedReport)
            .options(
                selectinload(TaskExecutionSelectedReport.execution_data)
            )
            .where(TaskExecutionSelectedReport.id == selected_report_id)
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def get_school_name_by_month_item_id(
            db: AsyncSession,
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
            .where(User.id == user_id)
            .where(SchoolStaffRole.school_id == school_id)
            .where(SchoolStaffRole.is_active.is_(True))
            .limit(1)
        )

        row = result.one_or_none()

        if row is None:
            return None

        return CheckerInfoDTO(
            full_name=row.full_name,
            post=row.role.label_kz,
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
    async def get_document_by_selected_report(
            db: AsyncSession,
            *,
            selected_report_id: int,
            user_id: int,
    ) -> TaskExecutionDocument | None:
        result = await db.execute(
            select(TaskExecutionDocument)
            .where(TaskExecutionDocument.selected_report_id == selected_report_id)
            .where(TaskExecutionDocument.uploaded_by_user_id == user_id)
            .where(TaskExecutionDocument.is_current.is_(True))
        )
        return result.scalar_one_or_none()
