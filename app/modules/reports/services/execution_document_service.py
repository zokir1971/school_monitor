# app/modules/reports/services/execution_document_service.py
from __future__ import annotations

import logging

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import get_storage
from app.core.storage.school_storage import SchoolStorageService
from app.modules.reports.enums import (
    DocumentType,
    TaskDocumentSource,
    TaskDocumentStatus,
)
from app.modules.reports.models_documents import TaskExecutionDocument
from app.modules.reports.repositories.execution_document_repo import (
    ExecutionDocumentRepo,
)
from app.modules.reports.repositories.execution_repo import ExecutionRepo
from app.modules.users.enums import UserRole

logger = logging.getLogger(__name__)


class ExecutionDocumentService:
    """
    Бизнес-логика итоговых документов выполнения задачи.

    Отвечает за:
    - загрузку и замену итогового файла;
    - работу с SchoolStorageService;
    - удаление замененного файла после успешного commit;
    - получение документа с проверкой доступа.
    """

    @staticmethod
    async def _delete_replaced_document_file(
            *,
            storage_service: SchoolStorageService,
            object_key: str,
    ) -> None:
        """
        Удаляет заменённый файл только в том случае,
        если он сохранён через новую архитектуру.

        Старые пути пока не удаляем автоматически:
        - uploads/task_execution/...
        - uploads/task_documents/...
        - media/reports/...
        """

        normalized_key = (
            object_key
            .replace("\\", "/")
            .lstrip("/")
        )

        try:
            await storage_service.delete(
                object_key=normalized_key,
            )

        except FileNotFoundError:

            logger.warning(

                "Заменяемый файл уже отсутствует: %s",

                normalized_key,

            )

        # noinspection PyBroadException
        except Exception:

            logger.exception(

                "Не удалось удалить заменённый файл: %s",

                normalized_key,

            )

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
        storage_service = SchoolStorageService(
            storage=get_storage(),
        )

        # 1. Проверка доступа
        has_access = await ExecutionRepo.user_has_access_to_month_item(
            db,
            month_item_id=month_item_id,
            user_id=user_id,
        )

        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Нет доступа к задаче",
            )

        # 2. Блокировка задачи
        locked_task = await ExecutionDocumentRepo.lock_task_row(
            db,
            month_item_id=month_item_id,
        )

        if locked_task is None:
            raise HTTPException(404, "Задача не найдена")
        if any(str(getattr(locked_task[k], 'value', locked_task[k])) == 'archived' for k in ('month_status', 'annual_status')):
            raise ValueError("Архивную задачу изменять нельзя.")
        if locked_task['completed_at'] or str(getattr(locked_task['status'], 'value', locked_task['status'])) in ('done', 'reviewed'):
            raise ValueError("Задача завершена. Используйте замену документа с указанием причины.")
        if required_document_id is not None:
            required = await ExecutionRepo.get_required_documents_for_task(db, month_item_id=month_item_id)
            if required_document_id not in {item.id for item in required}:
                raise ValueError("Документ не относится к этой задаче.")

        content = await upload_file.read(SchoolStorageService.MAX_FILE_SIZE + 1)
        if not content:
            raise ValueError("Файл пуст.")
        if len(content) > SchoolStorageService.MAX_FILE_SIZE:
            raise ValueError("Размер файла превышает 20 МБ.")
        if len(upload_file.filename or "document") > 255:
            raise ValueError("Имя файла слишком длинное.")

        # 3. Контекст школы для object key
        storage_context = (
            await ExecutionDocumentRepo.get_storage_context_for_month_item(
                db,
                month_item_id=month_item_id,
            )
        )

        if storage_context is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "Не удалось определить контекст хранения "
                    "для задачи"
                ),
            )

        # 4. Получаем текущий итоговый документ
        existing_doc = await ExecutionDocumentRepo.get_uploaded_document(
            db,
            month_item_id=month_item_id,
            required_document_id=required_document_id,
            document_type=document_type,
        )

        old_object_key = (
            str(existing_doc.file_path)
            if existing_doc and existing_doc.file_path
            else None
        )

        # 5. Создаём запись документа либо подготавливаем существующую
        doc = await ExecutionDocumentRepo.prepare_final_document(
            db,
            month_item_id=month_item_id,
            required_document_id=required_document_id,
            document_type=document_type,
            uploaded_by_user_id=user_id,
            source=TaskDocumentSource.UPLOAD,
            status=TaskDocumentStatus.SUBMITTED,
        )

        # flush нужен, чтобы получить doc.id без commit
        await db.flush()

        original_file_name = (
                upload_file.filename
                or "document"
        )

        content_type = (
                upload_file.content_type
                or "application/octet-stream"
        )

        stored_file = None
        commit_started = False

        try:
            # 6. Физическое сохранение файла
            stored_file = await storage_service.save_final_document(
                context=storage_context,
                document_id=doc.id,
                content=content,
                original_file_name=original_file_name,
                content_type=content_type,
            )

            # 7. Заполняем файловые поля документа
            await ExecutionDocumentRepo.update_document_file_data(
                db,
                document=doc,
                original_file_name=(
                    stored_file.original_file_name
                ),
                stored_file_name=(
                    stored_file.stored_file_name
                ),
                file_path=stored_file.object_key,
                mime_type=stored_file.content_type,
                file_size=stored_file.file_size,
            )

            await ExecutionDocumentRepo.refresh_before_commit(db, document=doc)
            commit_started = True
            await db.commit()

        except Exception:
            await db.rollback()

            remove_new = not commit_started
            if stored_file is not None and commit_started:
                from app.modules.reports.repositories.document_correction_repo import DocumentCorrectionRepo
                try:
                    remove_new = not await DocumentCorrectionRepo.referenced(db, stored_file.object_key)
                except Exception:
                    logger.exception("Commit outcome unknown; preserving uploaded final document")
                    remove_new = False
            if stored_file is not None and remove_new:
                try:
                    await storage_service.delete(
                        object_key=stored_file.object_key,
                    )
                except Exception:
                    logger.exception(
                        "Не удалось удалить новый файл после "
                        "ошибки сохранения документа в БД: %s",
                        stored_file.object_key,
                    )

            raise

        # 8. Старый файл удаляем только после успешного commit
        if (
                old_object_key
                and old_object_key != stored_file.object_key
        ):
            from app.modules.reports.repositories.document_correction_repo import DocumentCorrectionRepo
            try:
                if not await DocumentCorrectionRepo.referenced(db, old_object_key):
                    await cls._delete_replaced_document_file(
                        storage_service=storage_service,
                        object_key=old_object_key,
                    )
            except Exception:
                logger.exception("Could not clean replaced final document after successful commit")

        return doc

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
        document = await ExecutionDocumentRepo.get_document_by_id(
            db,
            document_id=document_id,
        )
        if not document:
            return None

        def check_feature():
            from app.core.feature_access import ensure_report,FeatureUnavailable
            from app.core.feature_flags import assessment_enabled,snapshot_has_assessment
            ensure_report(document.report_code)
            if not assessment_enabled() and snapshot_has_assessment(document.schema_json):raise FeatureUnavailable()
        if user_role == UserRole.SCHOOL_ADMIN:
            from app.modules.reports.repositories.document_correction_repo import DocumentCorrectionRepo
            if not await DocumentCorrectionRepo.admin_owns_document(db, document_id=document_id, user_id=user_id):return None
            check_feature()
            return document

        has_access = await ExecutionRepo.user_has_access_to_month_item(
            db,
            month_item_id=document.month_item_id,
            user_id=user_id,
        )
        if not has_access:
            return None

        check_feature()
        return document
