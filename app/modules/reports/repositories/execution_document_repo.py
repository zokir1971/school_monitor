# app/modules/reports/repositories/execution_document_repo.py
from __future__ import annotations


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload, selectinload, load_only

from app.core.storage.schemas import SchoolStorageContext
from app.modules.org.models import School
from app.modules.planning.models_month_plan import SchoolMonthPlan, SchoolMonthPlanItem
from app.modules.planning.models_school import SchoolPlan
from app.modules.reports.enums import (
    DocumentType,
    ReportTemplateMode,
    TaskDocumentSource,
    TaskDocumentStatus,
)
from app.modules.reports.models_documents import TaskExecutionDocument
from app.modules.reports.models_template_reports import UserReportTemplate


class ExecutionDocumentRepo:
    """
    Repository итоговых документов выполнения задачи.

    Отвечает за:
    - получение итоговых TaskExecutionDocument;
    - блокировку строки задачи перед заменой файла;
    - создание/подготовку текущего итогового документа;
    - обновление файловых метаданных;
    - получение storage-контекста задачи.
    """

    @staticmethod
    async def get_current_report_document(
            db: AsyncSession,
            *,
            selected_report_id: int,
    ) -> TaskExecutionDocument | None:
        """
        Получить текущий рабочий документ выбранного отчета.
        """
        stmt = (
            select(TaskExecutionDocument).options(raiseload("*"))
            .where(
                TaskExecutionDocument.selected_report_id == selected_report_id,
                TaskExecutionDocument.is_final.is_(False),
            )
            .order_by(
                TaskExecutionDocument.is_current.desc(),
                TaskExecutionDocument.id.desc(),
            )
            .limit(1)
        )
        return await db.scalar(stmt)

    @staticmethod
    async def get_current_report_documents_map(
            db: AsyncSession,
            *,
            selected_report_ids: list[int],
    ) -> dict[int, TaskExecutionDocument]:
        """
        Пакетно получить текущие рабочие документы
        для набора выбранных отчетов.
        """

        if not selected_report_ids:
            return {}


        stmt = (
            select(TaskExecutionDocument).options(raiseload("*"))
            .where(
                TaskExecutionDocument.selected_report_id.in_(
                    selected_report_ids
                ),
                TaskExecutionDocument.is_final.is_(False),
            )
            .options(
                load_only(
                    TaskExecutionDocument.id,
                    TaskExecutionDocument.selected_report_id,
                    TaskExecutionDocument.status,
                    TaskExecutionDocument.file_path,
                    TaskExecutionDocument.source,
                    TaskExecutionDocument.custom_template_id,
                    TaskExecutionDocument.template_mode,
                )
            )
            .order_by(
                TaskExecutionDocument.selected_report_id.asc(),
                TaskExecutionDocument.is_current.desc(),
                TaskExecutionDocument.id.desc(),
            )
        )


        result = await db.execute(stmt)


        documents = result.scalars().all()


        documents_map: dict[
            int,
            TaskExecutionDocument,
        ] = {}

        for document in documents:
            selected_report_id = (
                document.selected_report_id
            )

            if selected_report_id is None:
                continue

            selected_report_id = int(
                selected_report_id
            )

            if selected_report_id not in documents_map:
                documents_map[
                    selected_report_id
                ] = document


        return documents_map

    @staticmethod
    async def get_current_report_document_for_user(
            db: AsyncSession,
            *,
            selected_report_id: int,
            user_id: int,
    ) -> TaskExecutionDocument | None:
        """
        Получить текущий рабочий документ выбранного отчета
        для конкретного пользователя.
        """
        stmt = (
            select(TaskExecutionDocument).options(raiseload("*"))
            .where(
                TaskExecutionDocument.selected_report_id == selected_report_id,
                TaskExecutionDocument.uploaded_by_user_id == user_id,
                TaskExecutionDocument.is_final.is_(False),
                TaskExecutionDocument.is_current.is_(True),
            )
            .order_by(
                TaskExecutionDocument.id.desc(),
            )
            .limit(1)
        )

        return await db.scalar(stmt)

    @staticmethod
    async def apply_user_template_snapshot(
            db: AsyncSession,
            *,
            document: TaskExecutionDocument,
            user_template: UserReportTemplate,
    ) -> TaskExecutionDocument:
        """
        Применить snapshot пользовательского шаблона к рабочему документу.
        """
        document.custom_template_id = user_template.id
        document.template_mode = ReportTemplateMode.CUSTOM.value
        document.custom_content_html = user_template.content_html
        document.custom_content_text = user_template.content_text
        document.schema_json = user_template.schema_json
        document.status = TaskDocumentStatus.DRAFT

        await db.flush()
        return document

    @classmethod
    async def get_final_documents_for_task(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> list[TaskExecutionDocument]:
        """
        Получить итоговые документы по задаче.

        Что грузим:
        - только документы этой задачи
        - только итоговые документы
        - пользователей uploaded_by / submitted_by / reviewed_by по selectinload

        Почему так:
        - это список документов для экрана завершения
        - не тянем month_item и другие лишние связи
        - selectinload на user-связях предотвращает N+1
        """
        stmt = (
            select(TaskExecutionDocument).options(raiseload("*"))
            .where(TaskExecutionDocument.month_item_id == month_item_id)
            .where(TaskExecutionDocument.is_final.is_(True))
            .order_by(TaskExecutionDocument.created_at.desc(), TaskExecutionDocument.id.desc())
            .options(
                selectinload(TaskExecutionDocument.uploaded_by_user),
                selectinload(TaskExecutionDocument.submitted_by_user),
                selectinload(TaskExecutionDocument.reviewed_by_user),
                selectinload(TaskExecutionDocument.required_document),
            )
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def get_current_final_document_for_task(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> TaskExecutionDocument | None:
        stmt = (
            select(TaskExecutionDocument).options(raiseload("*"))
            .where(TaskExecutionDocument.month_item_id == month_item_id)
            .where(TaskExecutionDocument.is_final.is_(True))
            .where(TaskExecutionDocument.is_current.is_(True))
            .order_by(TaskExecutionDocument.created_at.desc(), TaskExecutionDocument.id.desc()).limit(1)
        )

        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def lock_task_row(
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> dict | None:
        """
        блокируем одну задачу, а не всю таблицу
        не даём двум upload одновременно:
        создать 2 записи
        перезаписать друг друга
        """
        stmt = (
            select(SchoolMonthPlanItem.id, SchoolMonthPlanItem.status, SchoolMonthPlanItem.completed_at,
                   SchoolMonthPlanItem.is_included, SchoolMonthPlan.status.label("month_status"),
                   SchoolPlan.status.label("annual_status"))
            .join(SchoolMonthPlan, SchoolMonthPlan.id == SchoolMonthPlanItem.month_plan_id)
            .join(SchoolPlan, SchoolPlan.id == SchoolMonthPlan.school_plan_id)
            .where(SchoolMonthPlanItem.id == month_item_id)
            .with_for_update(of=SchoolMonthPlanItem)
        )
        row = (await db.execute(stmt)).mappings().one_or_none()
        return dict(row) if row else None

    @classmethod
    async def prepare_final_document(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            required_document_id: int | None,
            document_type: DocumentType,
            uploaded_by_user_id: int | None,
            source: TaskDocumentSource,
            status: TaskDocumentStatus,
    ) -> TaskExecutionDocument:
        """
        Создать или подготовить текущий итоговый документ.

        На этом этапе файловые поля ещё не заполняются.
        После flush документ получает id, который используется
        для построения object_key в SchoolStorageService.
        """

        existing_doc = await cls.get_uploaded_document(
            db,
            month_item_id=month_item_id,
            required_document_id=required_document_id,
            document_type=document_type,
        )

        if existing_doc is not None:
            existing_doc.required_document_id = required_document_id
            existing_doc.document_type = document_type
            existing_doc.status = status
            existing_doc.source = source
            existing_doc.uploaded_by_user_id = uploaded_by_user_id

            existing_doc.is_current = True
            existing_doc.is_final = True
            existing_doc.version = 1

            await db.flush()

            return existing_doc

        new_doc = TaskExecutionDocument(
            month_item_id=month_item_id,
            required_document_id=required_document_id,
            document_type=document_type,
            status=status,
            source=source,
            version=1,
            is_current=True,
            is_final=True,
            uploaded_by_user_id=uploaded_by_user_id,
        )

        db.add(new_doc)
        await db.flush()

        return new_doc

    @staticmethod
    async def update_document_file_data(
            db: AsyncSession,
            *,
            document: TaskExecutionDocument,
            original_file_name: str,
            stored_file_name: str,
            file_path: str,
            mime_type: str,
            file_size: int,
    ) -> TaskExecutionDocument:
        """
        Заполнить файловые поля после успешного сохранения
        файла через SchoolStorageService.
        """

        document.title = original_file_name
        document.original_file_name = original_file_name
        document.stored_file_name = stored_file_name
        document.file_path = file_path
        document.mime_type = mime_type
        document.file_size = file_size

        await db.flush()

        return document

    @staticmethod
    async def get_storage_context_for_month_item(
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> SchoolStorageContext | None:
        """
        Получить контекст хранения для документа задачи.

        Цепочка:
        SchoolMonthPlanItem
            -> month_plan
            -> school_plan
            -> school
            -> district
        """

        stmt = (
            select(SchoolMonthPlanItem).options(raiseload("*"))
            .where(
                SchoolMonthPlanItem.id == month_item_id
            )
            .options(
                selectinload(
                    SchoolMonthPlanItem.month_plan
                )
                .selectinload(
                    SchoolMonthPlan.school_plan
                )
                .selectinload(
                    SchoolPlan.school
                )
                .selectinload(
                    School.district
                )
            )
        )

        month_item = await db.scalar(stmt)

        if month_item is None:
            return None

        month_plan = month_item.month_plan
        if month_plan is None:
            return None

        school_plan = month_plan.school_plan
        if school_plan is None:
            return None

        school = school_plan.school
        if school is None:
            return None

        district = school.district
        if district is None:
            return None

        return SchoolStorageContext(
            region_id=district.region_id,
            district_id=district.id,
            school_id=school.id,
            academic_year=school_plan.academic_year,
            school_plan_id=school_plan.id,
            month_item_id=month_item.id,
        )

    @classmethod
    async def get_document_by_id(
            cls,
            db: AsyncSession,
            *,
            document_id: int,
    ) -> TaskExecutionDocument | None:
        """
        Получить документ по id без проверки доступа.

        Подгружаем только то, что реально нужно для view/download.
        """
        stmt = (
            select(TaskExecutionDocument).options(raiseload("*"))
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
    async def get_uploaded_document(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            required_document_id: int | None,
            document_type: DocumentType,
    ) -> TaskExecutionDocument | None:
        """
        Получить текущий загруженный итоговый документ
        для конкретного required_document и типа.

        ВАЖНО:
        - строго фильтруем по required_document_id
        - строго фильтруем по document_type
        - только upload
        """
        stmt = (
            select(TaskExecutionDocument).options(raiseload("*"))
            .where(TaskExecutionDocument.month_item_id == month_item_id)
            .where(TaskExecutionDocument.is_final.is_(True))
            .where(TaskExecutionDocument.is_current.is_(True))
            .where(TaskExecutionDocument.source == TaskDocumentSource.UPLOAD)
            .where(TaskExecutionDocument.document_type == document_type)
        )

        if required_document_id is None:
            stmt = stmt.where(TaskExecutionDocument.required_document_id.is_(None))
        else:
            stmt = stmt.where(TaskExecutionDocument.required_document_id == required_document_id)

        stmt = stmt.order_by(TaskExecutionDocument.id.desc()).limit(1)

        result = await db.execute(stmt)
        return result.scalar_one_or_none()


    @staticmethod
    async def refresh_before_commit(db, *, document):
        await db.flush()
        await db.refresh(document)
