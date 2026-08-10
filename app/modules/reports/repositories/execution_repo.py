# app/modules/reports/repositories/execution_repo.py
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.planning.enums import PlanItemStatus
from app.modules.planning.models_month_plan import (
    SchoolMonthPlanItem,
    SchoolMonthPlanItemAssignee,
)
from app.modules.planning.models_school import (
    SchoolPlanRow11,
    SchoolPlanRow11RequiredDocument,
)
from app.modules.reports.enums import DocumentType, TaskDocumentStatus
from app.modules.reports.models_documents import (
    TaskExecutionData,
    TaskExecutionDocument,
    TaskExecutionSelectedReport,
)
from app.modules.staff.models_staff_school import SchoolStaffMember, SchoolStaffRole
from app.modules.users.models import User


class ExecutionRepo:
    """
    Repository жизненного цикла выполнения задачи.

    Отвечает за:
    - TaskExecutionData;
    - выбранные системные отчеты;
    - обязательные документы;
    - проверку доступа исполнителя;
    - проверку готовности системных отчетов к завершению задачи.

    Не отвечает за файловый lifecycle итоговых документов.
    Для него используется ExecutionDocumentRepo.
    """

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
        Получить список выбранных системных отчетов, которые еще не заполнены.

        analytical_reference / Анықтама не проверяем здесь,
        потому что это итоговый документ, а не системный отчет.
        """

        execution_data = await cls.get_execution_data_for_task(
            db,
            month_item_id=month_item_id,
        )

        if not execution_data or not execution_data.selected_reports:
            return []

        selected_codes_by_label: dict[str, str] = {}

        excluded_codes = {
            "analytical_reference",
        }

        for item in execution_data.selected_reports:
            if not item.report_type:
                continue

            code = str(item.report_type.code or "").strip()
            if not code:
                continue

            if code in excluded_codes:
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
                TaskExecutionDocument.document_type == DocumentType.REPORT,
                TaskExecutionDocument.report_code.in_(selected_codes),
                TaskExecutionDocument.status.in_([
                    TaskDocumentStatus.SUBMITTED,
                    TaskDocumentStatus.ACCEPTED,
                ]),
            )
        )

        completed_result = await db.execute(completed_stmt)
        completed_codes = {
            str(code).strip()
            for code in completed_result.scalars().all()
            if code
        }

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
