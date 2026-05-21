# app/modules/reports/report_service.py

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

from fastapi import UploadFile, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import get_storage
from app.modules.planning.enums import PlanItemStatus, ReviewPlace
from app.modules.reports.enums import DocumentType, TaskDocumentSource, TaskDocumentStatus, TaskCompletionMode
from app.modules.reports.models_documents import TaskExecutionData, TaskExecutionDocument, ReportTypeModel
from app.modules.reports.report_repo import ReportRepo
from app.modules.reports.report_schemas import (
    CurrentDraftDTO,
    ExecutionFormDTO,
)
from app.modules.users.enums import UserRole

logger = logging.getLogger(__name__)


class ReportService:
    """
    Сервис reports-domain для подготовки DTO страницы исполнения.

    Важно:
    - сервис не работает с доступами staff
    - сервис не читает задачу month_item
    - сервис только преобразует report-related модели в DTO
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

    @staticmethod
    def _normalize_str_list(value) -> list[str]:
        """
        Привести значение к списку строк.

        Ожидается, что в модели это может быть:
        - None
        - list[str]
        - tuple[str, ...]
        - list[int] / list[enum] / смешанные значения

        Для шаблона и JS всегда возвращаем list[str].
        """
        if not value:
            return []

        if isinstance(value, (list, tuple, set)):
            return [str(item) for item in value if item not in (None, "")]
        return [str(value)]

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

            key = (int(report_type_id), str(report_code))

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

    @staticmethod
    def build_current_draft_dto(
            current_draft: TaskExecutionDocument | None,
    ) -> CurrentDraftDTO:
        """
        Построить DTO текущего черновика.

        Если черновика нет:
        - exists=False
        - document_id=None

        Если есть:
        - exists=True
        - передаем id
        """
        if not current_draft:
            return CurrentDraftDTO(
                exists=False,
                document_id=None,
            )

        return CurrentDraftDTO(
            exists=True,
            document_id=getattr(current_draft, "id", None),
        )

    @classmethod
    async def get_execution_bundle_dto(
            cls,
            db,
            *,
            month_item_id: int,
    ) -> tuple[ExecutionFormDTO, CurrentDraftDTO]:
        """
        Получить execution-часть страницы уже в виде DTO.

        Что делает:
        1. получает bundle из ReportRepo
        2. превращает execution_data в ExecutionFormDTO
        3. превращает current_draft в CurrentDraftDTO

        Зачем нужен отдельный метод:
        - StaffTasksService остается тоньше
        - mapping report-domain сосредоточен в одном месте
        """
        bundle = await ReportRepo.get_execution_page_bundle(
            db,
            month_item_id=month_item_id,
        )

        execution = cls.build_execution_form_dto(bundle.execution_data)
        current_draft = cls.build_current_draft_dto(bundle.current_draft)

        return execution, current_draft

    @staticmethod
    async def _get_report_type_map(db: AsyncSession) -> dict[str, int]:
        rows = await db.execute(
            select(ReportTypeModel.id, ReportTypeModel.code)
        )
        return {code: id_ for id_, code in rows.all()}

    @staticmethod
    def _parse_generated_reports_json(
            generated_reports_json: str,
            report_type_map: dict[str, int],
    ) -> list[dict]:
        raw = (generated_reports_json or "").strip() or "[]"

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Некорректный формат generated_reports_json.") from exc

        if not isinstance(data, list):
            raise ValueError("generated_reports_json должен быть списком.")

        grouped: dict[int, dict] = {}

        for item in data:
            if not isinstance(item, dict):
                continue

            report_type_code = str(item.get("report_type") or "").strip()
            if not report_type_code:
                continue

            report_type_id = report_type_map.get(report_type_code)
            if not report_type_id:
                logger.warning(
                    "Пропущен неизвестный report_type code: %s",
                    report_type_code,
                )
                continue

            bucket = grouped.setdefault(
                report_type_id,
                {
                    "report_type_id": report_type_id,
                    "targets": [],
                    "_seen": set(),
                },
            )

            # Общий материал
            if bool(item.get("is_common")):
                dedup_key = ("common", "common")
                if dedup_key not in bucket["_seen"]:
                    bucket["_seen"].add(dedup_key)
                    bucket["targets"].append(
                        {
                            "target_kind": "common",
                            "target_value": "common",
                            "target_label": "Общий материал",
                        }
                    )
                continue

            # Материал по учителю
            teacher_id = str(item.get("teacher_id") or "").strip()
            teacher_name = str(item.get("teacher_name") or "").strip()

            if teacher_id:
                dedup_key = ("teacher", teacher_id)
                if dedup_key not in bucket["_seen"]:
                    bucket["_seen"].add(dedup_key)
                    bucket["targets"].append(
                        {
                            "target_kind": "teacher",
                            "target_value": teacher_id,
                            "target_label": teacher_name or teacher_id,
                        }
                    )
                continue

            # Универсальный fallback, если фронт когда-то начнет отправлять targets
            raw_targets = item.get("targets")
            if isinstance(raw_targets, list):
                for target in raw_targets:
                    if not isinstance(target, dict):
                        continue

                    target_kind = str(
                        target.get("target_kind")
                        or target.get("kind")
                        or ""
                    ).strip()

                    target_value = str(
                        target.get("target_value")
                        or target.get("value")
                        or ""
                    ).strip()

                    target_label = str(
                        target.get("target_label")
                        or target.get("label")
                        or target_value
                        or ""
                    ).strip()

                    if not target_kind or not target_value:
                        continue

                    dedup_key = (target_kind, target_value)
                    if dedup_key in bucket["_seen"]:
                        continue

                    bucket["_seen"].add(dedup_key)
                    bucket["targets"].append(
                        {
                            "target_kind": target_kind,
                            "target_value": target_value,
                            "target_label": target_label or target_value,
                        }
                    )

        result: list[dict] = []

        for item in grouped.values():
            targets = item["targets"]
            if not targets:
                continue

            result.append(
                {
                    "report_type_id": item["report_type_id"],
                    "targets": targets,
                }
            )

        result.sort(key=lambda x: x["report_type_id"])
        return result

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
        task = await ReportRepo.get_executor_month_item_for_execution(
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

        execution_data = await ReportRepo.get_or_create_execution_data(
            db,
            month_item_id=month_item_id,
        )

        execution_data.control_scope = control_scope or None
        execution_data.control_form = control_form or None
        execution_data.control_kind = control_kind or None
        execution_data.review_result = review_result or None

        report_type_map = await cls._get_report_type_map(db)

        # ✅ получаем map teacher_id -> full_name
        teacher_label_map = await ReportRepo.get_teacher_labels_by_ids(
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

        await ReportRepo.replace_selected_reports(
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
        task = await ReportRepo.get_executor_month_item_for_execution(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
        )

        if not task:
            raise ValueError("Задача не найдена или недоступна.")

        execution_data = await ReportRepo.get_execution_data_for_task(
            db,
            month_item_id=month_item_id,
        )

        execution_dto = cls.build_execution_form_dto(execution_data)

        required_documents = await ReportRepo.get_required_documents_for_task(
            db,
            month_item_id=month_item_id,
        )

        final_documents = await ReportRepo.get_final_documents_for_task(
            db,
            month_item_id=month_item_id,
        )

        current_final_document = await ReportRepo.get_current_final_document_for_task(
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
    async def upload_final_document(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
            required_document_id: int | None = None,
            upload_file: UploadFile,
            document_type: DocumentType,
    ):
        storage = get_storage()

        # 1. Проверка доступа
        has_access = await ReportRepo.user_has_access_to_month_item(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
        )

        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Нет доступа к задаче",
            )

        # 🔒 2. Блокировка строки (защита от гонок)
        await ReportRepo.lock_task_row(
            db,
            month_item_id=month_item_id,
        )

        # 3. Найти текущий документ
        existing_doc = await ReportRepo.get_uploaded_document(
            db,
            month_item_id=month_item_id,
            required_document_id=required_document_id,
            document_type=document_type,
        )

        old_path = existing_doc.file_path if existing_doc else None

        # 4. Читаем файл
        content = await upload_file.read()

        # 5. Сохраняем новый файл
        new_path, stored_name = storage.save(
            content,
            upload_file.filename or "document",
        )

        try:
            # 6. Обновляем БД
            doc = await ReportRepo.create_or_replace_final_document(
                db,
                month_item_id=month_item_id,
                required_document_id=required_document_id,
                document_type=document_type,
                original_file_name=upload_file.filename,
                stored_file_name=stored_name,
                file_path=new_path,
                mime_type=upload_file.content_type,
                file_size=len(content),
                uploaded_by_user_id=user_id,
                source=TaskDocumentSource.UPLOAD,
                status=TaskDocumentStatus.SUBMITTED,
            )

            await db.commit()

        except Exception:
            # ❗ откат БД
            await db.rollback()

            # ❗ удалить новый файл
            storage.delete(new_path)

            raise

        # 7. Удалить старый файл (НЕ критично)
        if old_path:
            try:
                storage.delete(old_path)
            except FileNotFoundError:
                # файл уже удалён — это не ошибка
                logger.warning("Old file already deleted: %s", old_path)
            except OSError as e:
                # проблемы с файловой системой
                logger.error("Failed to delete old file %s: %s", old_path, e)

        return doc

    @classmethod
    async def complete_task_execution(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
            completion_mode: TaskCompletionMode,
    ):
        task = await ReportRepo.get_executor_month_item_for_execution(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
        )

        if not task:
            raise ValueError("Задача не найдена или недоступна.")

        if task.status == PlanItemStatus.DONE:
            raise ValueError("Задача уже завершена.")

        final_document = await ReportRepo.get_current_final_document_for_task(
            db,
            month_item_id=month_item_id,
        )

        if not final_document:
            raise ValueError("Сначала загрузите итоговый документ.")

        execution = await ReportRepo.get_or_create_execution_data(
            db,
            month_item_id=month_item_id,
        )

        execution.completion_mode = completion_mode.value
        db.add(execution)

        if completion_mode == TaskCompletionMode.FINAL_WITH_SYSTEM_REPORTS:
            missing_reports = await ReportRepo.get_missing_selected_reports(
                db,
                month_item_id=month_item_id,
            )

            if missing_reports:
                raise ValueError(
                    "Не заполнены выбранные отчеты: "
                    + ", ".join(missing_reports)
                )

            await ReportRepo.mark_current_system_reports_submitted(
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

    @staticmethod
    async def _save_uploaded_file(
            *,
            month_item_id: int,
            upload_file: UploadFile,
    ) -> dict:
        """
        Здесь вставь свою реальную файловую логику.
        Метод должен вернуть словарь с метаданными файла.
        """
        content = await upload_file.read()

        # TODO: замени на свою файловую инфраструктуру
        stored_file_name = upload_file.filename
        file_path = f"/uploads/reports/{month_item_id}/{stored_file_name}"

        return {
            "original_file_name": upload_file.filename,
            "stored_file_name": stored_file_name,
            "file_path": file_path,
            "mime_type": upload_file.content_type or "application/octet-stream",
            "file_size": len(content),
        }

    @classmethod
    async def get_document_for_access(
            cls,
            db: AsyncSession,
            *,
            document_id: int,
            user_id: int,
            user_role: UserRole | None = None,
    ) -> TaskExecutionDocument | None:
        """
        Получить документ с проверкой доступа.

        Логика:
        1. ищем документ
        2. если это SCHOOL_ADMIN -> доступ разрешен
        3. иначе проверяем доступ к month_item документа
        """
        document = await ReportRepo.get_document_by_id(
            db,
            document_id=document_id,
        )
        if not document:
            return None

        if user_role == UserRole.SCHOOL_ADMIN:
            return document

        has_access = await ReportRepo.user_has_access_to_month_item(
            db,
            month_item_id=document.month_item_id,
            user_id=user_id,
        )
        if not has_access:
            return None

        return document
