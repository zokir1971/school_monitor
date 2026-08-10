# app/modules/reports/services/execution_service.py
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import PlanItemStatus, ReviewPlace
from app.modules.reports.enums import TaskCompletionMode, TaskDocumentStatus
from app.modules.reports.models_documents import TaskExecutionData
from app.modules.reports.schemas.execution_dto import ExecutionFormDTO
from app.modules.reports.repositories.execution_document_repo import (
    ExecutionDocumentRepo,
)
from app.modules.reports.repositories.execution_repo import ExecutionRepo
from app.modules.reports.repositories.report_type_repo import ReportTypeRepo


class ExecutionService:
    """
    Бизнес-логика выполнения задачи.

    Отвечает за:
    - построение execution DTO;
    - сохранение черновика выполнения;
    - подготовку данных страницы выполнения;
    - завершение задачи.

    Файловый lifecycle итоговых документов вынесен
    в ExecutionDocumentService.
    """

    @staticmethod
    def _normalize_text(value) -> str:
        """
        Привести значение к строке для UI.

        Почему нужно:
        - шаблон и JS не должны получать None
        - пустые строки нормализуются в ""
        """
        if value is None:
            return ""
        value = str(value).strip()
        return value or ""

    @classmethod
    def build_execution_form_dto(
            cls,
            execution_data: TaskExecutionData | None,
    ) -> ExecutionFormDTO:
        """
        Построить ExecutionFormDTO из ORM-модели TaskExecutionData.

        Что переносим:
        - control_scope / control_form / control_kind
        - review_result
        - generated_reports_json из relation selected_reports
        - производные списки subjects / class_groups / parallel_classes / teacher_ids
        - teacher_id как строку, если выбран ровно один учитель

        Если execution_data отсутствует:
        - возвращаем пустой DTO
        """
        if not execution_data:
            return ExecutionFormDTO()

        grouped: dict[tuple[int, str], dict] = {}

        report_types: list[str] = []
        subjects: list[str] = []
        class_groups: list[str] = []
        parallel_classes: list[str] = []
        teacher_ids: list[str] = []

        for item in getattr(execution_data, "selected_reports", []) or []:
            report_type = getattr(item, "report_type", None)
            if not report_type:
                continue

            report_type_id = getattr(report_type, "id", None)
            report_code = getattr(report_type, "code", None)

            if report_type_id is None or not report_code:
                continue

            report_code = str(report_code)
            if report_code not in report_types:
                report_types.append(report_code)

            key = (int(report_type_id), report_code)

            if key not in grouped:
                grouped[key] = {
                    "report_type_id": int(report_type_id),
                    "report_code": str(report_code),
                    "report_label": (
                            getattr(report_type, "name_kz", None)
                            or getattr(report_type, "name_ru", None)
                            or str(report_code)
                    ),
                    "targets": [],
                }

            target_kind = cls._normalize_text(getattr(item, "target_kind", None))
            target_value = cls._normalize_text(getattr(item, "target_value", None))
            target_label = (
                    cls._normalize_text(getattr(item, "target_label", None))
                    or target_value
            )

            if not target_kind or not target_value:
                continue

            grouped[key]["targets"].append(
                {
                    "kind": target_kind,
                    "value": target_value,
                    "label": target_label,
                }
            )

            if target_kind == "subject":
                if target_value not in subjects:
                    subjects.append(target_value)

            elif target_kind == "class_group":
                if target_value not in class_groups:
                    class_groups.append(target_value)

            elif target_kind == "parallel_class":
                if target_value not in parallel_classes:
                    parallel_classes.append(target_value)

            elif target_kind == "teacher":
                if target_value not in teacher_ids:
                    teacher_ids.append(target_value)

        teacher_id = teacher_ids[0] if len(teacher_ids) == 1 else ""

        return ExecutionFormDTO(
            control_scope=cls._normalize_text(getattr(execution_data, "control_scope", None)),
            control_form=cls._normalize_text(getattr(execution_data, "control_form", None)),
            control_kind=cls._normalize_text(getattr(execution_data, "control_kind", None)),
            review_result=cls._normalize_text(getattr(execution_data, "review_result", None)),
            report_types=report_types,
            subjects=subjects,
            class_groups=class_groups,
            parallel_classes=parallel_classes,
            teacher_id=teacher_id,
            teacher_ids=teacher_ids,
            generated_reports_json=json.dumps(
                list(grouped.values()),
                ensure_ascii=False,
            ),
        )

    @classmethod
    async def save_execution_draft(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
            control_scope: str,
            control_form: str,
            control_kind: str,
            review_result: str,
            report_types: list[str] | None = None,
            subjects: list[str] | None = None,
            class_groups: list[str] | None = None,
            parallel_classes: list[str] | None = None,
            teacher_ids: list[str] | None = None,
            teacher_id: str | None = None,
    ) -> TaskExecutionData:
        task = await ExecutionRepo.get_executor_month_item_for_execution(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
        )
        if not task:
            raise ValueError("Задача недоступна для сохранения черновика.")

        report_types = report_types or []
        subjects = subjects or []
        class_groups = class_groups or []
        parallel_classes = parallel_classes or []
        teacher_ids = teacher_ids or []
        teacher_id = (teacher_id or "").strip()

        execution_data = await ExecutionRepo.get_or_create_execution_data(
            db,
            month_item_id=month_item_id,
        )

        execution_data.control_scope = control_scope or None
        execution_data.control_form = control_form or None
        execution_data.control_kind = control_kind or None
        execution_data.review_result = review_result or None

        report_type_map = await ReportTypeRepo.get_code_id_map(db)

        # ✅ получаем map teacher_id -> full_name
        teacher_label_map = await ExecutionRepo.get_teacher_labels_by_ids(
            db,
            teacher_ids=teacher_ids + ([teacher_id] if teacher_id else []),
        )

        selected_reports: list[dict] = []

        for report_code in report_types:
            report_type_id = report_type_map.get(str(report_code))
            if not report_type_id:
                continue

            targets: list[dict] = []

            if control_scope == "subject":
                for subject in subjects:
                    subject = str(subject).strip()
                    if not subject:
                        continue

                    targets.append(
                        {
                            "target_kind": "subject",
                            "target_value": subject,
                            "target_label": subject,
                        }
                    )

                for tid in teacher_ids:
                    tid = str(tid).strip()
                    if not tid:
                        continue

                    targets.append(
                        {
                            "target_kind": "teacher",
                            "target_value": tid,
                            "target_label": teacher_label_map.get(tid, tid),
                        }
                    )

            elif control_scope == "teacher":
                for tid in teacher_ids:
                    tid = str(tid).strip()
                    if not tid:
                        continue

                    targets.append(
                        {
                            "target_kind": "teacher",
                            "target_value": tid,
                            "target_label": teacher_label_map.get(tid, tid),
                        }
                    )

            elif control_scope == "class":
                for class_group in class_groups:
                    class_group = str(class_group).strip()
                    if not class_group:
                        continue

                    targets.append(
                        {
                            "target_kind": "class_group",
                            "target_value": class_group,
                            "target_label": class_group,
                        }
                    )

                for tid in teacher_ids:
                    tid = str(tid).strip()
                    if not tid:
                        continue

                    targets.append(
                        {
                            "target_kind": "teacher",
                            "target_value": tid,
                            "target_label": teacher_label_map.get(tid, tid),
                        }
                    )

            elif control_scope == "parallel":
                for parallel_class in parallel_classes:
                    parallel_class = str(parallel_class).strip()
                    if not parallel_class:
                        continue

                    targets.append(
                        {
                            "target_kind": "parallel_class",
                            "target_value": parallel_class,
                            "target_label": parallel_class,
                        }
                    )

                for tid in teacher_ids:
                    tid = str(tid).strip()
                    if not tid:
                        continue

                    targets.append(
                        {
                            "target_kind": "teacher",
                            "target_value": tid,
                            "target_label": teacher_label_map.get(tid, tid),
                        }
                    )

            elif teacher_id:
                targets.append(
                    {
                        "target_kind": "teacher",
                        "target_value": teacher_id,
                        "target_label": teacher_label_map.get(teacher_id, teacher_id),
                    }
                )

            selected_reports.append(
                {
                    "report_type_id": int(report_type_id),
                    "targets": targets,
                }
            )

        await ExecutionRepo.replace_selected_reports(
            db,
            execution_data_id=execution_data.id,
            selected_reports=selected_reports,
        )

        await db.commit()
        await db.refresh(execution_data)

        return execution_data

    @classmethod
    async def get_execution_page_data(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
    ) -> dict:
        task = await ExecutionRepo.get_executor_month_item_for_execution(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
        )

        if not task:
            raise ValueError("Задача не найдена или недоступна.")

        execution_data = await ExecutionRepo.get_execution_data_for_task(
            db,
            month_item_id=month_item_id,
        )

        execution_dto = cls.build_execution_form_dto(execution_data)

        required_documents = await ExecutionRepo.get_required_documents_for_task(
            db,
            month_item_id=month_item_id,
        )

        final_documents = await ExecutionDocumentRepo.get_final_documents_for_task(
            db,
            month_item_id=month_item_id,
        )

        current_final_document = await ExecutionDocumentRepo.get_current_final_document_for_task(
            db,
            month_item_id=month_item_id,
        )

        is_done = task.status == PlanItemStatus.DONE

        completion_ready = bool(execution_data) and len(required_documents) > 0

        review_place_text = "—"

        if getattr(task, "review_places", None):
            values = []

            for item in task.review_places:
                review_place = getattr(item, "review_place", None)

                if not review_place:
                    continue

                try:
                    enum_place = ReviewPlace(review_place)
                    values.append(enum_place.label_kz)

                except ValueError:
                    values.append(str(review_place))
            if values:
                review_place_text = ", ".join(values)

        task_topic = (
                getattr(getattr(task, "source_row11", None), "topic", None)
                or "—"
        )

        task_goal = (
                getattr(getattr(task, "source_row11", None), "goal", None)
                or "—"
        )

        return {
            "task": task,
            "task_topic": task_topic,
            "task_goal": task_goal,

            "review_place_text": review_place_text,

            "execution": execution_dto,

            "required_documents": required_documents,
            "final_documents": final_documents,
            "current_final_document": current_final_document,

            "has_final_document": current_final_document is not None,
            "final_document_status": (
                current_final_document.status
                if current_final_document
                else None
            ),

            "completion_ready": completion_ready,
            "is_done": is_done,
        }

    @classmethod
    async def complete_task_execution(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
            completion_mode: TaskCompletionMode,
    ):
        task = await ExecutionRepo.get_executor_month_item_for_execution(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
        )

        if not task:
            raise ValueError("Задача не найдена или недоступна.")

        if task.status == PlanItemStatus.DONE:
            raise ValueError("Задача уже завершена.")

        final_document = await ExecutionDocumentRepo.get_current_final_document_for_task(
            db,
            month_item_id=month_item_id,
        )

        if not final_document:
            raise ValueError("Сначала загрузите итоговый документ.")

        execution = await ExecutionRepo.get_or_create_execution_data(
            db,
            month_item_id=month_item_id,
        )

        execution.completion_mode = completion_mode.value
        db.add(execution)

        if completion_mode == TaskCompletionMode.FINAL_WITH_SYSTEM_REPORTS:
            missing_reports = await ExecutionRepo.get_missing_selected_reports(
                db,
                month_item_id=month_item_id,
            )

            if missing_reports:
                raise ValueError(
                    "Не заполнены выбранные отчеты: "
                    + ", ".join(missing_reports)
                )

            await ExecutionRepo.mark_current_system_reports_submitted(
                db,
                month_item_id=month_item_id,
                user_id=user_id,
            )

        now = datetime.now(timezone.utc)

        task.status = PlanItemStatus.DONE
        task.executed_at = date.today()
        task.completed_at = now
        task.completed_by_user_id = user_id

        final_document.status = TaskDocumentStatus.SUBMITTED
        final_document.submitted_by_user_id = user_id
        final_document.submitted_at = now

        db.add(task)
        db.add(final_document)

        await db.commit()
