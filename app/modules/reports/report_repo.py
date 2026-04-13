from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.planning.enums import PlanItemStatus
from app.modules.planning.models_month_plan import (
    SchoolMonthPlanItem,
    SchoolMonthPlanItemAssignee, SchoolMonthPlanItemReviewPlace,
)
from app.modules.planning.models_school import (
    SchoolPlanRow11,
    SchoolPlanRow11RequiredDocument,
)
from app.modules.reports.enums import TaskDocumentSource, TaskDocumentStatus
from app.modules.reports.models_documents import ReportTypeModel, TaskExecutionDocument, TaskExecutionData, \
    TaskExecutionDataReportType
from app.modules.staff.models_staff_school import SchoolStaffRole, SchoolStaffMember
from app.modules.users.models import User


class ReportRepo:
    @staticmethod
    def _task_with_relations_stmt():
        execution_documents_load = selectinload(SchoolMonthPlanItem.execution_documents)
        execution_data_load = selectinload(SchoolMonthPlanItem.execution_data)

        return (
            select(SchoolMonthPlanItem)
            .options(
                selectinload(SchoolMonthPlanItem.source_row11).selectinload(
                    SchoolPlanRow11.required_documents
                ),

                execution_documents_load.selectinload(
                    TaskExecutionDocument.required_document
                ),
                execution_documents_load.selectinload(
                    TaskExecutionDocument.uploaded_by_user
                ),
                execution_documents_load.selectinload(
                    TaskExecutionDocument.submitted_by_user
                ),
                execution_documents_load.selectinload(
                    TaskExecutionDocument.reviewed_by_user
                ),

                execution_data_load.selectinload(
                    TaskExecutionData.report_type_links
                ).selectinload(
                    TaskExecutionDataReportType.report_type
                ),

                selectinload(SchoolMonthPlanItem.assignees).selectinload(
                    SchoolMonthPlanItemAssignee.staff_role
                ),

                selectinload(SchoolMonthPlanItem.review_places),
            )
        )

    @staticmethod
    def _apply_executor_user_filter(stmt, *, user_id: int):
        """
        Оставляем только те задачи, где текущий пользователь назначен исполнителем.
        Фильтр должен идти через assignees -> staff_role -> staff_member -> user_account.
        """
        return stmt.where(
            SchoolMonthPlanItem.assignees.any(
                SchoolMonthPlanItemAssignee.staff_role.has(
                    SchoolStaffRole.is_active.is_(True),
                )
            ),
            SchoolMonthPlanItem.assignees.any(
                SchoolMonthPlanItemAssignee.staff_role.has(
                    SchoolStaffRole.staff_member.has(
                        SchoolStaffMember.is_active.is_(True)
                    )
                )
            ),
            SchoolMonthPlanItem.assignees.any(
                SchoolMonthPlanItemAssignee.staff_role.has(
                    SchoolStaffRole.staff_member.has(
                        SchoolStaffMember.user_account.has(User.id == user_id)
                    )
                )
            ),
        )

    @classmethod
    async def get_month_item_with_required_documents(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> SchoolMonthPlanItem | None:
        stmt = cls._task_with_relations_stmt().where(
            SchoolMonthPlanItem.id == month_item_id
        )

        result = await db.execute(stmt)
        return result.scalars().unique().one_or_none()

    @classmethod
    async def get_executor_month_item(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
    ) -> SchoolMonthPlanItem | None:
        stmt = cls._task_with_relations_stmt().where(
            SchoolMonthPlanItem.id == month_item_id
        )
        stmt = cls._apply_executor_user_filter(stmt, user_id=user_id)

        result = await db.execute(stmt)
        return result.scalars().unique().one_or_none()

    @classmethod
    async def get_executor_month_item_by_status(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
            allowed_statuses: Iterable[PlanItemStatus],
    ) -> SchoolMonthPlanItem | None:
        stmt = cls._task_with_relations_stmt().where(
            SchoolMonthPlanItem.id == month_item_id,
            SchoolMonthPlanItem.status.in_(list(allowed_statuses)),
        )
        stmt = cls._apply_executor_user_filter(stmt, user_id=user_id)

        result = await db.execute(stmt)
        return result.scalars().unique().one_or_none()

    @classmethod
    async def get_required_document_for_task(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            required_document_id: int,
    ) -> SchoolPlanRow11RequiredDocument | None:
        stmt = (
            select(SchoolPlanRow11RequiredDocument)
            .join(
                SchoolPlanRow11,
                SchoolPlanRow11.id == SchoolPlanRow11RequiredDocument.row11_id,
            )
            .join(
                SchoolMonthPlanItem,
                SchoolMonthPlanItem.source_row11_id == SchoolPlanRow11.id,
            )
            .where(SchoolMonthPlanItem.id == month_item_id)
            .where(SchoolPlanRow11RequiredDocument.id == required_document_id)
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_required_documents_for_task(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> list[SchoolPlanRow11RequiredDocument]:
        stmt = (
            select(SchoolPlanRow11RequiredDocument)
            .join(
                SchoolPlanRow11,
                SchoolPlanRow11.id == SchoolPlanRow11RequiredDocument.row11_id,
            )
            .join(
                SchoolMonthPlanItem,
                SchoolMonthPlanItem.source_row11_id == SchoolPlanRow11.id,
            )
            .where(SchoolMonthPlanItem.id == month_item_id)
            .order_by(SchoolPlanRow11RequiredDocument.id.asc())
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def get_required_documents_for_month_item(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> list[SchoolPlanRow11RequiredDocument]:
        """
        Алиас под сервис.
        """
        return await cls.get_required_documents_for_task(
            db,
            month_item_id=month_item_id,
        )

    @classmethod
    async def get_current_document(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            required_document_id: int | None,
            document_type,
            source: TaskDocumentSource,
            is_final: bool,
    ) -> TaskExecutionDocument | None:
        stmt = (
            select(TaskExecutionDocument)
            .where(TaskExecutionDocument.month_item_id == month_item_id)
            .where(TaskExecutionDocument.document_type == document_type)
            .where(TaskExecutionDocument.source == source)
            .where(TaskExecutionDocument.is_final.is_(is_final))
            .where(TaskExecutionDocument.is_current.is_(True))
            .options(
                selectinload(TaskExecutionDocument.required_document),
                selectinload(TaskExecutionDocument.uploaded_by_user),
                selectinload(TaskExecutionDocument.submitted_by_user),
                selectinload(TaskExecutionDocument.reviewed_by_user),
            )
            .order_by(
                TaskExecutionDocument.version.desc(),
                TaskExecutionDocument.id.desc(),
            )
        )

        if required_document_id is None:
            stmt = stmt.where(TaskExecutionDocument.required_document_id.is_(None))
        else:
            stmt = stmt.where(
                TaskExecutionDocument.required_document_id == required_document_id
            )

        result = await db.execute(stmt)
        return result.scalars().first()

    @classmethod
    async def get_document_by_id(
            cls,
            db: AsyncSession,
            *,
            document_id: int,
    ) -> TaskExecutionDocument | None:
        stmt = (
            select(TaskExecutionDocument)
            .where(TaskExecutionDocument.id == document_id)
            .options(
                selectinload(TaskExecutionDocument.required_document),
                selectinload(TaskExecutionDocument.uploaded_by_user),
                selectinload(TaskExecutionDocument.submitted_by_user),
                selectinload(TaskExecutionDocument.reviewed_by_user),
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_documents_for_task(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            only_current: bool | None = None,
    ) -> list[TaskExecutionDocument]:
        stmt = (
            select(TaskExecutionDocument)
            .where(TaskExecutionDocument.month_item_id == month_item_id)
            .options(
                selectinload(TaskExecutionDocument.required_document),
                selectinload(TaskExecutionDocument.uploaded_by_user),
                selectinload(TaskExecutionDocument.submitted_by_user),
                selectinload(TaskExecutionDocument.reviewed_by_user),
            )
            .order_by(
                TaskExecutionDocument.document_type.asc(),
                TaskExecutionDocument.version.desc(),
                TaskExecutionDocument.created_at.desc(),
            )
        )

        if only_current is True:
            stmt = stmt.where(TaskExecutionDocument.is_current.is_(True))
        elif only_current is False:
            stmt = stmt.where(TaskExecutionDocument.is_current.is_(False))

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def get_current_final_documents_for_task(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> list[TaskExecutionDocument]:
        stmt = (
            select(TaskExecutionDocument)
            .where(TaskExecutionDocument.month_item_id == month_item_id)
            .where(TaskExecutionDocument.is_current.is_(True))
            .where(TaskExecutionDocument.is_final.is_(True))
            .options(
                selectinload(TaskExecutionDocument.required_document),
                selectinload(TaskExecutionDocument.uploaded_by_user),
                selectinload(TaskExecutionDocument.submitted_by_user),
                selectinload(TaskExecutionDocument.reviewed_by_user),
            )
            .order_by(
                TaskExecutionDocument.document_type.asc(),
                TaskExecutionDocument.version.desc(),
                TaskExecutionDocument.created_at.desc(),
            )
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def get_next_version(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            required_document_id: int | None,
            document_type,
    ) -> int:
        stmt = (
            select(func.coalesce(func.max(TaskExecutionDocument.version), 0))
            .where(TaskExecutionDocument.month_item_id == month_item_id)
            .where(TaskExecutionDocument.document_type == document_type)
        )

        if required_document_id is None:
            stmt = stmt.where(TaskExecutionDocument.required_document_id.is_(None))
        else:
            stmt = stmt.where(
                TaskExecutionDocument.required_document_id == required_document_id
            )

        result = await db.execute(stmt)
        max_version = result.scalar_one()
        return int(max_version) + 1

    @classmethod
    async def mark_not_current_documents(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            required_document_id: int | None,
            document_type,
            sources: Iterable[TaskDocumentSource] | None = None,
            final_only: bool | None = None,
    ) -> None:
        stmt = (
            update(TaskExecutionDocument)
            .where(TaskExecutionDocument.month_item_id == month_item_id)
            .where(TaskExecutionDocument.document_type == document_type)
            .where(TaskExecutionDocument.is_current.is_(True))
            .values(is_current=False)
        )

        if required_document_id is None:
            stmt = stmt.where(TaskExecutionDocument.required_document_id.is_(None))
        else:
            stmt = stmt.where(
                TaskExecutionDocument.required_document_id == required_document_id
            )

        if sources:
            stmt = stmt.where(TaskExecutionDocument.source.in_(list(sources)))

        if final_only is True:
            stmt = stmt.where(TaskExecutionDocument.is_final.is_(True))
        elif final_only is False:
            stmt = stmt.where(TaskExecutionDocument.is_final.is_(False))

        await db.execute(stmt)

    @classmethod
    async def create_document(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            required_document_id: int | None,
            document_type,
            source: TaskDocumentSource,
            status: TaskDocumentStatus,
            version: int,
            is_current: bool,
            is_final: bool,
            title: str | None = None,
            original_file_name: str | None = None,
            stored_file_name: str | None = None,
            file_path: str | None = None,
            mime_type: str | None = None,
            file_size: int | None = None,
            content_html: str | None = None,
            review_comment: str | None = None,
            uploaded_by_user_id: int | None = None,
            submitted_by_user_id: int | None = None,
            reviewed_by_user_id: int | None = None,
            submitted_at=None,
            reviewed_at=None,
    ) -> TaskExecutionDocument:
        doc = TaskExecutionDocument(
            month_item_id=month_item_id,
            required_document_id=required_document_id,
            document_type=document_type,
            source=source,
            status=status,
            version=version,
            is_current=is_current,
            is_final=is_final,
            title=title,
            original_file_name=original_file_name,
            stored_file_name=stored_file_name,
            file_path=file_path,
            mime_type=mime_type,
            file_size=file_size,
            content_html=content_html,
            review_comment=review_comment,
            uploaded_by_user_id=uploaded_by_user_id,
            submitted_by_user_id=submitted_by_user_id,
            reviewed_by_user_id=reviewed_by_user_id,
            submitted_at=submitted_at,
            reviewed_at=reviewed_at,
        )
        db.add(doc)
        await db.flush()
        return doc

    @classmethod
    async def update_document_fields(
            cls,
            db: AsyncSession,
            *,
            document: TaskExecutionDocument,
            title: str | None = None,
            status: TaskDocumentStatus | None = None,
            content_html: str | None = None,
            review_comment: str | None = None,
            original_file_name: str | None = None,
            stored_file_name: str | None = None,
            file_path: str | None = None,
            mime_type: str | None = None,
            file_size: int | None = None,
            uploaded_by_user_id: int | None = None,
            submitted_by_user_id: int | None = None,
            reviewed_by_user_id: int | None = None,
            submitted_at=None,
            reviewed_at=None,
            is_current: bool | None = None,
            is_final: bool | None = None,
    ) -> TaskExecutionDocument:
        if title is not None:
            document.title = title
        if status is not None:
            document.status = status
        if content_html is not None:
            document.content_html = content_html
        if review_comment is not None:
            document.review_comment = review_comment
        if original_file_name is not None:
            document.original_file_name = original_file_name
        if stored_file_name is not None:
            document.stored_file_name = stored_file_name
        if file_path is not None:
            document.file_path = file_path
        if mime_type is not None:
            document.mime_type = mime_type
        if file_size is not None:
            document.file_size = file_size
        if uploaded_by_user_id is not None:
            document.uploaded_by_user_id = uploaded_by_user_id
        if submitted_by_user_id is not None:
            document.submitted_by_user_id = submitted_by_user_id
        if reviewed_by_user_id is not None:
            document.reviewed_by_user_id = reviewed_by_user_id
        if submitted_at is not None:
            document.submitted_at = submitted_at
        if reviewed_at is not None:
            document.reviewed_at = reviewed_at

        if is_current is not None:
            document.is_current = is_current
        if is_final is not None:
            document.is_final = is_final

        await db.flush()
        return document

    @classmethod
    async def get_report_type(
            cls,
            db: AsyncSession,
            *,
            report_type_id: int,
    ) -> ReportTypeModel | None:
        stmt = select(ReportTypeModel).where(ReportTypeModel.id == report_type_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_active_report_types(
            cls,
            db: AsyncSession,
    ) -> list[ReportTypeModel]:
        stmt = (
            select(ReportTypeModel)
            .where(ReportTypeModel.is_active.is_(True))
            .order_by(ReportTypeModel.sort_order.asc(), ReportTypeModel.id.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def has_final_document_for_completion(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            allowed_statuses: Iterable[TaskDocumentStatus],
    ) -> bool:
        stmt = (
            select(TaskExecutionDocument.id)
            .where(TaskExecutionDocument.month_item_id == month_item_id)
            .where(TaskExecutionDocument.is_current.is_(True))
            .where(TaskExecutionDocument.is_final.is_(True))
            .where(TaskExecutionDocument.source == TaskDocumentSource.UPLOAD)
            .where(TaskExecutionDocument.required_document_id.is_not(None))
            .where(TaskExecutionDocument.status.in_(list(allowed_statuses)))
            .limit(1)
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None

    @classmethod
    async def has_final_document_for_required_document(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            required_document_id: int,
            allowed_statuses: Iterable[TaskDocumentStatus],
    ) -> bool:
        stmt = (
            select(TaskExecutionDocument.id)
            .where(TaskExecutionDocument.month_item_id == month_item_id)
            .where(TaskExecutionDocument.required_document_id == required_document_id)
            .where(TaskExecutionDocument.is_current.is_(True))
            .where(TaskExecutionDocument.is_final.is_(True))
            .where(TaskExecutionDocument.source == TaskDocumentSource.UPLOAD)
            .where(TaskExecutionDocument.status.in_(list(allowed_statuses)))
            .limit(1)
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None

    @classmethod
    async def count_final_documents_for_task(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            allowed_statuses: Iterable[TaskDocumentStatus] | None = None,
    ) -> int:
        stmt = (
            select(func.count(TaskExecutionDocument.id))
            .where(TaskExecutionDocument.month_item_id == month_item_id)
            .where(TaskExecutionDocument.is_current.is_(True))
            .where(TaskExecutionDocument.is_final.is_(True))
            .where(TaskExecutionDocument.source == TaskDocumentSource.UPLOAD)
        )

        if allowed_statuses:
            stmt = stmt.where(TaskExecutionDocument.status.in_(list(allowed_statuses)))

        result = await db.execute(stmt)
        return int(result.scalar_one())

    @classmethod
    async def set_month_item_status(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            status: PlanItemStatus,
    ) -> None:
        stmt = (
            update(SchoolMonthPlanItem)
            .where(SchoolMonthPlanItem.id == month_item_id)
            .values(status=status)
        )
        await db.execute(stmt)

    # получение текущего черновика
    @classmethod
    async def get_current_draft(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> TaskExecutionDocument | None:
        stmt = (
            select(TaskExecutionDocument)
            .where(
                TaskExecutionDocument.month_item_id == month_item_id,
                TaskExecutionDocument.is_current.is_(True),
                TaskExecutionDocument.is_final.is_(False),
            )
            .order_by(
                TaskExecutionDocument.version.desc(),
                TaskExecutionDocument.id.desc(),
            )
        )

        result = await db.execute(stmt)
        return result.scalars().first()

    @classmethod
    async def get_execution_data_for_task(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> TaskExecutionData | None:
        stmt = (
            select(TaskExecutionData)
            .where(TaskExecutionData.month_item_id == month_item_id)
            .options(
                selectinload(TaskExecutionData.report_type_links).selectinload(
                    TaskExecutionDataReportType.report_type
                )
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_or_create_execution_data(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> TaskExecutionData:
        execution_data = await cls.get_execution_data_for_task(
            db,
            month_item_id=month_item_id,
        )
        if execution_data:
            return execution_data

        execution_data = TaskExecutionData(month_item_id=month_item_id)
        db.add(execution_data)
        await db.flush()
        return execution_data

    @classmethod
    async def update_execution_data_fields(
            cls,
            db: AsyncSession,
            *,
            execution_data: TaskExecutionData,
            control_scope: str | None = None,
            control_form: str | None = None,
            control_kind: str | None = None,
            evidence_note: str | None = None,
            planned_review_place: str | None = None,
            reference_text: str | None = None,
            conclusion: str | None = None,
            recommendations: str | None = None,
            reference_file_note: str | None = None,
            review_result: str | None = None,
            notes: str | None = None,
    ) -> TaskExecutionData:
        execution_data.control_scope = control_scope
        execution_data.control_form = control_form
        execution_data.control_kind = control_kind
        execution_data.evidence_note = evidence_note
        execution_data.planned_review_place = planned_review_place
        execution_data.reference_text = reference_text
        execution_data.conclusion = conclusion
        execution_data.recommendations = recommendations
        execution_data.reference_file_note = reference_file_note
        execution_data.review_result = review_result
        execution_data.notes = notes

        await db.flush()
        return execution_data

    @classmethod
    async def replace_execution_data_report_types(
            cls,
            db: AsyncSession,
            *,
            execution_data: TaskExecutionData,
            report_type_ids: list[int],
    ) -> TaskExecutionData:
        await db.execute(
            delete(TaskExecutionDataReportType).where(
                TaskExecutionDataReportType.execution_data_id == execution_data.id
            )
        )

        for report_type_id in report_type_ids:
            db.add(
                TaskExecutionDataReportType(
                    execution_data_id=execution_data.id,
                    report_type_id=report_type_id,
                )
            )

        await db.flush()
        return execution_data

    @classmethod
    async def mark_month_item_as_not_executed(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> None:
        stmt = (
            update(SchoolMonthPlanItem)
            .where(SchoolMonthPlanItem.id == month_item_id)
            .values(status=PlanItemStatus.NOT_EXECUTED)
        )
        await db.execute(stmt)
