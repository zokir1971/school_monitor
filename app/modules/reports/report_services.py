from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from html import escape

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import PlanItemStatus
from app.modules.reports.enums import (
    DocumentType,
    TaskDocumentSource,
    TaskDocumentStatus,
)
from app.modules.reports.models_documents import TaskExecutionDocument
from app.modules.reports.report_repo import ReportRepo


@dataclass
class ExecutionTemplateData:
    control_scope: str | None = None
    control_form: str | None = None
    control_kind: str | None = None

    evidence_note: str | None = None
    planned_review_place: str | None = None

    reference_text: str | None = None
    conclusion: str | None = None
    recommendations: str | None = None

    reference_file_note: str | None = None
    review_result: str | None = None
    notes: str | None = None

    report_types: list[str] = field(default_factory=list)


class FileStorageService:
    @staticmethod
    async def save_task_execution_file(
        *,
        file_name: str,
        content: bytes,
    ) -> tuple[str, str]:
        import os
        import uuid

        os.makedirs("uploads/task_execution", exist_ok=True)
        ext = ""
        if "." in file_name:
            ext = "." + file_name.rsplit(".", 1)[-1]

        stored_file_name = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join("uploads/task_execution", stored_file_name)

        with open(file_path, "wb") as f:
            f.write(content)

        return stored_file_name, file_path


class ReportService:
    DONE_ALLOWED_DOCUMENT_STATUSES = {
        TaskDocumentStatus.SUBMITTED,
        TaskDocumentStatus.ACCEPTED,
        TaskDocumentStatus.APPROVED,
    }

    @classmethod
    def _normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @classmethod
    def _normalize_report_type_codes(
        cls,
        report_type_codes: list[str] | tuple[str, ...] | None,
    ) -> list[str]:
        if not report_type_codes:
            return []

        result: list[str] = []
        seen: set[str] = set()

        for code in report_type_codes:
            code_norm = cls._normalize_text(code)
            if not code_norm:
                continue
            if code_norm in seen:
                continue
            seen.add(code_norm)
            result.append(code_norm)

        return result

    @classmethod
    async def _get_report_type_ids_by_codes(
        cls,
        db: AsyncSession,
        *,
        report_type_codes: list[str] | None,
    ) -> list[int]:
        codes = cls._normalize_report_type_codes(report_type_codes)
        if not codes:
            return []

        active_report_types = await ReportRepo.get_active_report_types(db)
        code_to_id = {item.code: item.id for item in active_report_types}

        missing = [code for code in codes if code not in code_to_id]
        if missing:
            raise ValueError(
                f"Не найдены активные типы отчета: {', '.join(missing)}"
            )

        return [code_to_id[code] for code in codes]

    @classmethod
    def validate_reference_form(
        cls,
        *,
        reference_text: str | None,
        conclusion: str | None,
        recommendations: str | None,
    ) -> None:
        reference_text = cls._normalize_text(reference_text)
        conclusion = cls._normalize_text(conclusion)
        recommendations = cls._normalize_text(recommendations)

        if not reference_text:
            raise ValueError("Поле 'Текст справки' обязательно для заполнения")
        if not conclusion:
            raise ValueError("Поле 'Вывод' обязательно для заполнения")
        if not recommendations:
            raise ValueError("Поле 'Рекомендации' обязательно для заполнения")

    @classmethod
    def build_reference_html(
        cls,
        *,
        task_title: str | None,
        task_goal: str | None,
        review_place: str | None,
        reference_text: str | None,
        conclusion: str | None,
        recommendations: str | None,
    ) -> str:
        task_title = escape(task_title or "—")
        task_goal = escape(task_goal or "—")
        review_place = escape(review_place or "—")
        reference_text = escape(reference_text or "—").replace("\n", "<br>")
        conclusion = escape(conclusion or "—").replace("\n", "<br>")
        recommendations = escape(recommendations or "—").replace("\n", "<br>")

        return f"""
        <div class="generated-reference">
          <h2 style="text-align:center;">СПРАВКА</h2>

          <p><strong>Тема:</strong> {task_title}</p>
          <p><strong>Цель:</strong> {task_goal}</p>
          <p><strong>Место рассмотрения:</strong> {review_place}</p>

          <h3>Ход контроля</h3>
          <p>{reference_text}</p>

          <h3>Вывод</h3>
          <p>{conclusion}</p>

          <h3>Рекомендации</h3>
          <p>{recommendations}</p>
        </div>
        """.strip()

    @classmethod
    async def _get_required_documents_for_task(
        cls,
        db: AsyncSession,
        *,
        month_item_id: int,
    ) -> list:
        documents = await ReportRepo.get_required_documents_for_month_item(
            db,
            month_item_id=month_item_id,
        )
        return list(documents or [])

    @classmethod
    def build_execution_template_data(cls, execution_data) -> ExecutionTemplateData | None:
        return cls._build_execution_template_data(execution_data)

    @classmethod
    def _build_execution_template_data(cls, execution_data) -> ExecutionTemplateData | None:
        if not execution_data:
            return None

        report_types = [
            link.report_type.code
            for link in (execution_data.report_type_links or [])
            if link.report_type and link.report_type.code
        ]

        return ExecutionTemplateData(
            control_scope=execution_data.control_scope,
            control_form=execution_data.control_form,
            control_kind=execution_data.control_kind,
            evidence_note=execution_data.evidence_note,
            planned_review_place=execution_data.planned_review_place,
            reference_text=execution_data.reference_text,
            conclusion=execution_data.conclusion,
            recommendations=execution_data.recommendations,
            reference_file_note=execution_data.reference_file_note,
            review_result=execution_data.review_result,
            notes=execution_data.notes,
            report_types=report_types,
        )

    @classmethod
    async def get_task_for_execution(
        cls,
        db: AsyncSession,
        *,
        month_item_id: int,
        user_id: int,
    ):
        task = await ReportRepo.get_executor_month_item(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
        )
        if not task:
            raise ValueError("Задача не найдена или недоступна")

        if task.status not in {PlanItemStatus.IN_PROGRESS, PlanItemStatus.DONE}:
            raise ValueError("Эта задача недоступна для исполнения")

        return task

    @classmethod
    async def get_execution_page_data(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
            draft_document_type: DocumentType,
    ) -> dict:
        task = await cls.get_task_for_execution(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
        )

        required_documents = await cls._get_required_documents_for_task(
            db,
            month_item_id=task.id,
        )

        execution_data = await ReportRepo.get_execution_data_for_task(
            db,
            month_item_id=task.id,
        )
        execution = cls.build_execution_template_data(execution_data)

        current_draft = await ReportRepo.get_current_draft(
            db,
            month_item_id=task.id,
        )

        all_documents = await ReportRepo.get_documents_for_task(
            db,
            month_item_id=task.id,
            only_current=None,
        )

        current_documents = [doc for doc in all_documents if doc.is_current]
        final_documents = [doc for doc in current_documents if doc.is_final]

        completion_ready = await cls.can_mark_task_as_done(
            db,
            month_item_id=task.id,
        )

        source_row11 = getattr(task, "source_row11", None)

        task_topic = (
                getattr(task, "topic", None)
                or getattr(source_row11, "topic", None)
                or getattr(task, "name", None)
        )

        task_goal = (
                getattr(task, "goal", None)
                or getattr(source_row11, "goal", None)
        )

        review_place_text = None

        if getattr(task, "review_places", None):
            review_place_values: list[str] = []

            for rp in task.review_places:
                place = getattr(rp, "review_place", None)
                if not place:
                    continue

                value = getattr(place, "label_kz", None) or str(place)
                if value:
                    review_place_values.append(value)

            if review_place_values:
                review_place_text = ", ".join(review_place_values)

        if not review_place_text and execution and execution.planned_review_place:
            review_place_text = execution.planned_review_place

        return {
            "task": task,
            "task_topic": task_topic,
            "task_goal": task_goal,
            "review_place_text": review_place_text,
            "execution": execution,
            "required_documents": required_documents,
            "current_draft": current_draft,
            "current_documents": current_documents,
            "final_documents": final_documents,
            "completion_ready": completion_ready,
            "draft_document_type": draft_document_type,
        }

    @classmethod
    async def save_reference_draft(
        cls,
        db: AsyncSession,
        *,
        month_item_id: int,
        user_id: int,
        required_document_id: int,
        document_type: DocumentType,
        report_type_codes: list[str] | None,
        title: str | None,
        task_title: str | None,
        task_goal: str | None,
        review_place: str | None,
        control_scope: str | None,
        control_form: str | None,
        control_kind: str | None,
        evidence_note: str | None,
        planned_review_place: str | None,
        reference_text: str | None,
        conclusion: str | None,
        recommendations: str | None,
        reference_file_note: str | None,
        review_result: str | None,
        notes: str | None = None,
    ) -> TaskExecutionDocument:
        task = await ReportRepo.get_executor_month_item_by_status(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
            allowed_statuses=[PlanItemStatus.IN_PROGRESS],
        )
        if not task:
            raise ValueError("Задача не найдена или недоступна для редактирования")

        required_document = await ReportRepo.get_required_document_for_task(
            db,
            month_item_id=month_item_id,
            required_document_id=required_document_id,
        )
        if not required_document:
            raise ValueError("Указанный обязательный документ не относится к данной задаче")

        cls.validate_reference_form(
            reference_text=reference_text,
            conclusion=conclusion,
            recommendations=recommendations,
        )

        report_type_ids = await cls._get_report_type_ids_by_codes(
            db,
            report_type_codes=report_type_codes,
        )

        content_html = cls.build_reference_html(
            task_title=task_title,
            task_goal=task_goal,
            review_place=review_place,
            reference_text=reference_text,
            conclusion=conclusion,
            recommendations=recommendations,
        )

        title = cls._normalize_text(title) or "Справка"

        execution_data = await ReportRepo.get_or_create_execution_data(
            db,
            month_item_id=month_item_id,
        )
        await ReportRepo.update_execution_data_fields(
            db,
            execution_data=execution_data,
            control_scope=cls._normalize_text(control_scope),
            control_form=cls._normalize_text(control_form),
            control_kind=cls._normalize_text(control_kind),
            evidence_note=cls._normalize_text(evidence_note),
            planned_review_place=cls._normalize_text(planned_review_place),
            reference_text=cls._normalize_text(reference_text),
            conclusion=cls._normalize_text(conclusion),
            recommendations=cls._normalize_text(recommendations),
            reference_file_note=cls._normalize_text(reference_file_note),
            review_result=cls._normalize_text(review_result),
            notes=cls._normalize_text(notes),
        )
        await ReportRepo.replace_execution_data_report_types(
            db,
            execution_data=execution_data,
            report_type_ids=report_type_ids,
        )

        current_draft = await ReportRepo.get_current_document(
            db,
            month_item_id=month_item_id,
            required_document_id=required_document_id,
            document_type=document_type,
            source=TaskDocumentSource.GENERATED,
            is_final=False,
        )

        if current_draft:
            await ReportRepo.update_document_fields(
                db,
                document=current_draft,
                title=title,
                status=TaskDocumentStatus.DRAFT,
                content_html=content_html,
                review_comment=cls._normalize_text(reference_file_note),
                uploaded_by_user_id=user_id,
                is_current=True,
                is_final=False,
            )
            await db.commit()
            await db.refresh(current_draft)
            return current_draft

        version = await ReportRepo.get_next_version(
            db,
            month_item_id=month_item_id,
            required_document_id=required_document_id,
            document_type=document_type,
        )

        draft = await ReportRepo.create_document(
            db,
            month_item_id=month_item_id,
            required_document_id=required_document_id,
            document_type=document_type,
            source=TaskDocumentSource.GENERATED,
            status=TaskDocumentStatus.DRAFT,
            version=version,
            is_current=True,
            is_final=False,
            title=title,
            content_html=content_html,
            review_comment=cls._normalize_text(reference_file_note),
            uploaded_by_user_id=user_id,
        )
        await db.commit()
        await db.refresh(draft)
        return draft

    @classmethod
    async def upload_final_document(
        cls,
        db: AsyncSession,
        *,
        month_item_id: int,
        user_id: int,
        required_document_id: int,
        document_type: DocumentType,
        title: str | None,
        original_file_name: str,
        stored_file_name: str,
        file_path: str,
        mime_type: str | None,
        file_size: int | None,
        reference_file_note: str | None = None,
        review_result: str | None = None,
        auto_complete_task: bool = True,
    ) -> TaskExecutionDocument:
        task = await ReportRepo.get_executor_month_item_by_status(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
            allowed_statuses=[PlanItemStatus.IN_PROGRESS],
        )
        if not task:
            raise ValueError("Задача не найдена или недоступна для загрузки")

        required_document = await ReportRepo.get_required_document_for_task(
            db,
            month_item_id=month_item_id,
            required_document_id=required_document_id,
        )
        if not required_document:
            raise ValueError("Указанный обязательный документ не относится к данной задаче")

        if not original_file_name:
            raise ValueError("Не выбран файл для загрузки")
        if not stored_file_name or not file_path:
            raise ValueError("Файл не был сохранен корректно")

        execution_data = await ReportRepo.get_or_create_execution_data(
            db,
            month_item_id=month_item_id,
        )
        await ReportRepo.update_execution_data_fields(
            db,
            execution_data=execution_data,
            reference_file_note=cls._normalize_text(reference_file_note),
            review_result=cls._normalize_text(review_result),
        )

        await ReportRepo.mark_not_current_documents(
            db,
            month_item_id=month_item_id,
            required_document_id=required_document_id,
            document_type=document_type,
            sources=[TaskDocumentSource.UPLOAD],
            final_only=True,
        )

        version = await ReportRepo.get_next_version(
            db,
            month_item_id=month_item_id,
            required_document_id=required_document_id,
            document_type=document_type,
        )

        final_doc = await ReportRepo.create_document(
            db,
            month_item_id=month_item_id,
            required_document_id=required_document_id,
            document_type=document_type,
            source=TaskDocumentSource.UPLOAD,
            status=TaskDocumentStatus.SUBMITTED,
            version=version,
            is_current=True,
            is_final=True,
            title=cls._normalize_text(title) or "Итоговый документ",
            original_file_name=original_file_name,
            stored_file_name=stored_file_name,
            file_path=file_path,
            mime_type=mime_type,
            file_size=file_size,
            review_comment=cls._normalize_text(reference_file_note),
            uploaded_by_user_id=user_id,
            submitted_by_user_id=user_id,
            submitted_at=datetime.utcnow(),
        )

        if auto_complete_task:
            await cls.try_mark_task_as_done(
                db,
                month_item_id=month_item_id,
            )

        await db.commit()
        await db.refresh(final_doc)
        return final_doc

    @classmethod
    async def can_mark_task_as_done(
        cls,
        db: AsyncSession,
        *,
        month_item_id: int,
    ) -> bool:
        task = await ReportRepo.get_month_item_with_required_documents(
            db,
            month_item_id=month_item_id,
        )
        if not task:
            return False

        if task.status != PlanItemStatus.IN_PROGRESS:
            return False

        required_documents = await cls._get_required_documents_for_task(
            db,
            month_item_id=month_item_id,
        )
        if not required_documents:
            return False

        for required_document in required_documents:
            ok = await ReportRepo.has_final_document_for_required_document(
                db,
                month_item_id=month_item_id,
                required_document_id=required_document.id,
                allowed_statuses=cls.DONE_ALLOWED_DOCUMENT_STATUSES,
            )
            if not ok:
                return False

        return True

    @classmethod
    async def try_mark_task_as_done(
        cls,
        db: AsyncSession,
        *,
        month_item_id: int,
    ) -> bool:
        can_done = await cls.can_mark_task_as_done(
            db,
            month_item_id=month_item_id,
        )
        if not can_done:
            return False

        await ReportRepo.set_month_item_status(
            db,
            month_item_id=month_item_id,
            status=PlanItemStatus.DONE,
        )
        await db.flush()
        return True

    @classmethod
    async def get_task_with_draft(
        cls,
        db: AsyncSession,
        month_item_id: int,
        user_id: int,
    ):
        task = await cls.get_task_for_execution(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
        )

        draft = await ReportRepo.get_current_draft(
            db,
            month_item_id=month_item_id,
        )

        execution_data = await ReportRepo.get_execution_data_for_task(
            db,
            month_item_id=month_item_id,
        )

        return task, draft, cls._build_execution_template_data(execution_data)

    @classmethod
    async def mark_task_as_not_executed(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
            review_result: str | None = None,
            notes: str | None = None,
    ) -> bool:
        task = await ReportRepo.get_executor_month_item_by_status(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
            allowed_statuses=[PlanItemStatus.IN_PROGRESS],
        )
        if not task:
            raise ValueError("Задача не найдена или недоступна для изменения статуса")

        execution_data = await ReportRepo.get_or_create_execution_data(
            db,
            month_item_id=month_item_id,
        )

        current_review_result = getattr(execution_data, "review_result", None)
        current_notes = getattr(execution_data, "notes", None)

        new_review_result = cls._normalize_text(review_result)
        new_notes = cls._normalize_text(notes)

        if new_review_result is None:
            new_review_result = current_review_result
        if new_notes is None:
            new_notes = current_notes

        await ReportRepo.update_execution_data_fields(
            db,
            execution_data=execution_data,
            review_result=new_review_result,
            notes=new_notes,
        )

        await ReportRepo.mark_month_item_as_not_executed(
            db,
            month_item_id=month_item_id,
        )

        await db.flush()
        return True
