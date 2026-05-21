# app/modules/reports/report_repo.py
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.planning.enums import PlanItemStatus
from app.modules.planning.models_month_plan import SchoolMonthPlanItem, SchoolMonthPlanItemAssignee
from app.modules.planning.models_school import SchoolPlanRow11RequiredDocument, SchoolPlanRow11
from app.modules.reports.enums import DocumentType, TaskDocumentSource, TaskDocumentStatus
from app.modules.reports.models_documents import (
    TaskExecutionData,
    TaskExecutionDocument,
    TaskExecutionSelectedReport,
)
from app.modules.reports.report_schemas import ExecutionPageBundle
from app.modules.staff.models_staff_school import SchoolStaffRole, SchoolStaffMember
from app.modules.users.models import User


class ReportRepo:
    """
    Repo reports-domain для страницы исполнения задачи.

    Здесь оставлены только методы, которые реально нужны
    для staff_task_execute_details() и StaffTasksService.get_execution_page_payload().

    Что repo делает:
    - получает execution_data
    - получает current_draft
    - объединяет их в bundle

    Что repo не делает:
    - не собирает DTO
    - не знает про шаблон
    - не строит control_flow
    """

    @classmethod
    async def get_execution_page_bundle(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> ExecutionPageBundle:
        """
        Получить bundle данных execution-страницы.

        Зачем нужен:
        - сервису удобно получать execution_data и current_draft
          одной repo-точкой
        - сервис остается чище
        - внутреннюю реализацию можно позже оптимизировать
          без изменения сервисного слоя
        """
        current_draft = await cls.get_current_draft(
            db,
            month_item_id=month_item_id,
        )
        execution_data = await cls.get_execution_data_for_task(
            db,
            month_item_id=month_item_id,
        )

        return ExecutionPageBundle(
            current_draft=current_draft,
            execution_data=execution_data,
        )

    @classmethod
    async def get_current_draft(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> TaskExecutionDocument | None:
        """
        Получить текущий черновик по задаче.

        Логика:
        - только current
        - только не final
        - если черновиков несколько, берем самый свежий
          по version desc, id desc
        """
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
        """
        Получить execution_data для задачи.

        Что подгружаем:
        - report_type_links
        - report_type для каждого link

        Почему нужен selectinload:
        - чтобы service мог безопасно собрать report_types
          без дополнительных lazy-запросов
        """
        stmt = (
            select(TaskExecutionData)
            .where(TaskExecutionData.month_item_id == month_item_id)
            .options(
                selectinload(TaskExecutionData.selected_reports).selectinload(
                    TaskExecutionSelectedReport.report_type
                ),
            )
        )
        return await db.scalar(stmt)

    @classmethod
    async def get_executor_month_item_for_execution(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
    ) -> SchoolMonthPlanItem | None:
        stmt = (
            select(SchoolMonthPlanItem)
            .where(SchoolMonthPlanItem.id == month_item_id)
            .where(
                SchoolMonthPlanItem.status.in_(
                    [PlanItemStatus.TODO, PlanItemStatus.IN_PROGRESS, PlanItemStatus.DONE]
                )
            )
            .options(
                selectinload(SchoolMonthPlanItem.assignees),
            )
        )

        stmt = cls._apply_executor_user_filter(stmt, user_id=user_id)

        return await db.scalar(stmt)

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

        execution_data = TaskExecutionData(
            month_item_id=month_item_id,
        )
        db.add(execution_data)
        await db.flush()
        return execution_data

    @classmethod
    async def replace_selected_reports(
            cls,
            db: AsyncSession,
            *,
            execution_data_id: int,
            selected_reports: list[dict],
    ) -> None:
        await db.execute(
            delete(TaskExecutionSelectedReport).where(
                TaskExecutionSelectedReport.execution_data_id == execution_data_id
            )
        )

        new_rows: list[TaskExecutionSelectedReport] = []

        for item in selected_reports:
            report_type_id = item.get("report_type_id")
            if not report_type_id:
                continue

            targets = item.get("targets") or []
            for target in targets:
                target_kind = str(target.get("target_kind") or "").strip()
                target_value = str(target.get("target_value") or "").strip()
                target_label = str(target.get("target_label") or "").strip() or None

                if not target_kind or not target_value:
                    continue

                new_rows.append(
                    TaskExecutionSelectedReport(
                        execution_data_id=execution_data_id,
                        report_type_id=int(report_type_id),
                        target_kind=target_kind,
                        target_value=target_value,
                        target_label=target_label,
                    )
                )

        if new_rows:
            db.add_all(new_rows)

        await db.flush()

    @classmethod
    async def get_required_documents_for_task(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> list[SchoolPlanRow11RequiredDocument]:
        """
        Получить список обязательных документов для задачи.

        Что грузим:
        - только одну month-plan задачу
        - source_row11
        - required_documents у source_row11

        Почему так:
        - не делаем join на все подряд
        - selectinload хорошо масштабируется для 1 -> many
        - не тянем ненужные связи required_document дальше
        """
        stmt = (
            select(SchoolMonthPlanItem)
            .where(SchoolMonthPlanItem.id == month_item_id)
            .options(
                selectinload(SchoolMonthPlanItem.source_row11).selectinload(
                    SchoolPlanRow11.required_documents
                )
            )
        )

        result = await db.execute(stmt)
        task = result.scalar_one_or_none()
        if not task or not task.source_row11:
            return []

        required_documents = getattr(task.source_row11, "required_documents", None) or []
        return list(required_documents)

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
            select(TaskExecutionDocument)
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
            select(TaskExecutionDocument)
            .where(TaskExecutionDocument.month_item_id == month_item_id)
            .where(TaskExecutionDocument.is_final.is_(True))
            .where(TaskExecutionDocument.is_current.is_(True))
            .order_by(TaskExecutionDocument.created_at.desc(), TaskExecutionDocument.id.desc())
        )

        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def lock_task_row(
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> None:
        """
        блокируем одну задачу, а не всю таблицу
        не даём двум upload одновременно:
        создать 2 записи
        перезаписать друг друга
        """
        stmt = (
            select(SchoolMonthPlanItem.id)
            .where(SchoolMonthPlanItem.id == month_item_id)
            .with_for_update()
        )
        await db.execute(stmt)

    @classmethod
    async def create_or_replace_final_document(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            required_document_id: int | None,
            document_type: DocumentType,
            original_file_name: str | None,
            stored_file_name: str | None,
            file_path: str | None,
            mime_type: str | None,
            file_size: int | None,
            uploaded_by_user_id: int | None,
            source: TaskDocumentSource,
            status: TaskDocumentStatus,
    ) -> TaskExecutionDocument:

        # Ищем существующий итоговый документ (upload)
        existing_doc = await cls.get_uploaded_document(
            db,
            month_item_id=month_item_id,
            required_document_id=required_document_id,
            document_type=document_type,
        )

        if existing_doc:
            # ОБНОВЛЯЕМ существующую запись (никаких новых строк)

            existing_doc.required_document_id = required_document_id
            existing_doc.document_type = document_type
            existing_doc.status = status
            existing_doc.source = source

            existing_doc.title = original_file_name
            existing_doc.original_file_name = original_file_name
            existing_doc.stored_file_name = stored_file_name
            existing_doc.file_path = file_path
            existing_doc.mime_type = mime_type
            existing_doc.file_size = file_size

            existing_doc.uploaded_by_user_id = uploaded_by_user_id

            # гарантируем флаги
            existing_doc.is_current = True
            existing_doc.is_final = True

            # version НЕ трогаем (можно вообще всегда = 1 держать)
            existing_doc.version = 1

            await db.flush()
            return existing_doc

        # если нет — создаём ОДНУ запись
        new_doc = TaskExecutionDocument(
            month_item_id=month_item_id,
            required_document_id=required_document_id,
            document_type=document_type,
            status=status,
            source=source,
            version=1,  # всегда 1
            is_current=True,
            is_final=True,
            title=original_file_name,
            original_file_name=original_file_name,
            stored_file_name=stored_file_name,
            file_path=file_path,
            mime_type=mime_type,
            file_size=file_size,
            uploaded_by_user_id=uploaded_by_user_id,
        )

        db.add(new_doc)
        await db.flush()
        return new_doc

    @staticmethod
    def _apply_executor_user_filter(stmt, *, user_id: int):
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
    async def user_has_access_to_month_item(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
    ) -> bool:
        """
        Проверить, имеет ли пользователь доступ к задаче.
        """
        stmt = (
            select(SchoolMonthPlanItem.id)
            .where(SchoolMonthPlanItem.id == month_item_id)
        )
        stmt = cls._apply_executor_user_filter(stmt, user_id=user_id)

        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None

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
            select(TaskExecutionDocument)
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
    async def get_teacher_labels_by_ids(
            db: AsyncSession,
            *,
            teacher_ids: list[str],
    ) -> dict[str, str]:
        """
        возвращает ФИО учителя из SchoolStaffMember
        "target_kind": "teacher",
        "target_value": str(tid),
        "target_label": "Фамилия имя отчество"
        """
        if not teacher_ids:
            return {}

        teacher_ids_int = []
        for value in teacher_ids:
            try:
                teacher_ids_int.append(int(value))
            except (TypeError, ValueError):
                continue

        if not teacher_ids_int:
            return {}

        stmt = (
            select(SchoolStaffMember.id, SchoolStaffMember.full_name)
            .where(SchoolStaffMember.id.in_(teacher_ids_int))
        )

        rows = (await db.execute(stmt)).all()

        result: dict[str, str] = {}
        for teacher_id, full_name in rows:
            result[str(teacher_id)] = (full_name or str(teacher_id)).strip()

        return result

    @classmethod
    async def get_missing_selected_reports(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> list[str]:
        """
        Получить список выбранных отчетов, которые еще не заполнены.

        Используется при варианте завершения:
        FINAL_WITH_SYSTEM_REPORTS.

        Логика:
        - выбранные отчеты берем из TaskExecutionData.selected_reports;
        - фактически созданные отчеты берем из TaskExecutionDocument.report_code;
        - сравниваем по report_code;
        - возвращаем человекочитаемые названия отсутствующих отчетов.
        """

        execution_data = await cls.get_execution_data_for_task(
            db,
            month_item_id=month_item_id,
        )

        if not execution_data or not execution_data.selected_reports:
            return []

        selected_codes_by_label: dict[str, str] = {}

        for item in execution_data.selected_reports:
            if not item.report_type:
                continue

            code = str(item.report_type.code or "").strip()
            if not code:
                continue

            label = (
                    item.report_type.name_kz
                    or item.report_type.name_ru
                    or code
            )

            selected_codes_by_label[code] = label

        selected_codes = set(selected_codes_by_label.keys())

        if not selected_codes:
            return []

        completed_stmt = (
            select(TaskExecutionDocument.report_code)
            .where(
                TaskExecutionDocument.month_item_id == month_item_id,
                TaskExecutionDocument.is_current.is_(True),
                TaskExecutionDocument.is_final.is_(False),
                TaskExecutionDocument.report_code.in_(selected_codes),
                TaskExecutionDocument.status.in_([
                    TaskDocumentStatus.DRAFT,
                    TaskDocumentStatus.SUBMITTED,
                    TaskDocumentStatus.ACCEPTED,
                ]),
            )
        )

        completed_result = await db.execute(completed_stmt)
        completed_codes = set(completed_result.scalars().all())

        missing_codes = selected_codes - completed_codes

        return [
            selected_codes_by_label[code]
            for code in missing_codes
        ]

    @classmethod
    async def mark_current_system_reports_submitted(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
    ) -> None:
        """
        Отметить все текущие системные отчеты как отправленные.

        Используется при завершении задачи (вариант с системными отчетами).

        Что делает:
        - находит все НЕ итоговые документы (is_final=False)
        - только актуальные (is_current=True)
        - только системные отчеты (report_code != None)
        - переводит их в статус SUBMITTED
        - фиксирует кто и когда отправил

        Важно:
        - итоговый документ НЕ трогает
        - не создает новые записи
        - работает одним UPDATE (без N+1)
        """

        now = datetime.now(timezone.utc)

        stmt = (
            update(TaskExecutionDocument)
            .where(
                TaskExecutionDocument.month_item_id == month_item_id,
                TaskExecutionDocument.is_current.is_(True),
                TaskExecutionDocument.is_final.is_(False),
                TaskExecutionDocument.report_code.is_not(None),
            )
            .values(
                status=TaskDocumentStatus.SUBMITTED,
                submitted_by_user_id=user_id,
                submitted_at=now,
            )
        )

        await db.execute(stmt)
