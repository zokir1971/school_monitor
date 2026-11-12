from datetime import datetime, timezone
from pathlib import Path
import json
import logging
from fastapi import HTTPException
from app.core.storage import get_storage
from app.core.storage.school_storage import SchoolStorageService
from app.core.storage.key_builder import SchoolObjectKeyBuilder
from app.core.storage.schemas import StoredFile
from app.modules.reports.repositories.document_correction_repo import DocumentCorrectionRepo as Repo
from app.modules.reports.repositories.execution_document_repo import ExecutionDocumentRepo

logger = logging.getLogger(__name__)
def value(v):
    return getattr(v, 'value', v)

class DocumentCorrectionService:
    @staticmethod
    def allowed(user, tasks):
        if not tasks or not getattr(user, 'school_id', None):
            return False
        if any(t['school_id'] != user.school_id or value(t['annual_status']) == 'archived' or value(t['month_status']) == 'archived' for t in tasks):
            return False
        return value(user.role) == 'school_admin' or all(t['completed_by_user_id'] == user.id for t in tasks)

    @classmethod
    async def page(cls, db, *, user, month_item_id):
        tasks = await Repo.tasks(db, [month_item_id])
        if not cls.allowed(user, tasks):
            raise HTTPException(403, 'Изменять документы может администратор школы или сотрудник, завершивший задачу / Құжатты мектеп әкімшісі немесе тапсырманы аяқтаған қызметкер өзгерте алады')
        return await Repo.documents(db, month_item_id)

    @classmethod
    async def replace(cls, db, *, user, month_item_id, document_id, expected_key, reason, upload):
        reason = str(reason or '').strip()
        if not reason or len(reason) > 1000:
            raise HTTPException(400, 'Укажите причину замены (до 1000 символов) / Ауыстыру себебін көрсетіңіз')
        original = Path(str(getattr(upload, 'filename', '') or '').replace('\\', '/')).name
        ext = Path(original).suffix.lower()
        mime = {'.pdf':'application/pdf', '.doc':'application/msword', '.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xls':'application/vnd.ms-excel', '.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg'}
        if ext not in mime or len(original) > 255:
            raise HTTPException(400, 'Выберите PDF, Word, Excel или изображение / PDF, Word, Excel немесе суретті таңдаңыз')
        found = await Repo.target(db, document_id)
        if not found or found[0]['month_item_id'] != month_item_id:
            raise HTTPException(404, 'Документ не найден / Құжат табылмады')
        docs, protocols, tasks = await Repo.lock_target(db, document_id, found[1])
        if not cls.allowed(user, tasks):
            raise HTTPException(403, 'Нет права изменять все связанные задачи. Общий протокол заменяет администратор школы / Барлық байланысқан тапсырмаларды өзгертуге құқық жоқ')
        doc = next((d for d in docs if d['id'] == document_id), None)
        if doc is None or not doc['is_current'] or value(doc['source']) != 'upload':
            raise HTTPException(409, 'Можно заменять только текущий загруженный файл / Тек ағымдағы жүктелген файлды ауыстыруға болады')
        if doc['file_path'] != expected_key:
            raise HTTPException(409, 'Документ уже изменён. Обновите страницу / Құжат өзгерді. Бетті жаңартыңыз')
        if value(doc['document_type']) == 'protocol' and not protocols:
            raise HTTPException(409, 'Не найдена связь с протоколом рассмотрения / Қарау хаттамасымен байланыс табылмады')
        if protocols and ext not in ('.pdf','.doc','.docx'):
            raise HTTPException(400, 'Для протокола выберите PDF или Word / Хаттама үшін PDF немесе Word таңдаңыз')
        if protocols and (len(protocols) != len(found[1]) or any(p['protocol_file_path'] != expected_key for p in protocols)):
            raise HTTPException(409, 'Протокол уже изменён. Обновите страницу / Хаттама өзгерді')
        # Bounded upload; validation precedes any storage mutation.
        content = await upload.read(SchoolStorageService.MAX_FILE_SIZE + 1)
        if not content or len(content) > SchoolStorageService.MAX_FILE_SIZE:
            raise HTTPException(400, 'Файл пуст или больше 20 МБ / Файл бос немесе 20 МБ-тан үлкен')
        storage = get_storage()
        context = await ExecutionDocumentRepo.get_storage_context_for_month_item(db, month_item_id=month_item_id)
        if context is None:
            raise HTTPException(404, 'Не найден контекст хранения / Сақтау деректері табылмады')
        # Unique destination, even for simultaneous uploads of the same name.
        key, stored_name = SchoolObjectKeyBuilder.build_correction_key(context=context, original_file_name=original)
        old_keys = {d['file_path'] for d in docs if d['file_path']} | {p['protocol_file_path'] for p in protocols if p['protocol_file_path']}
        stamp = datetime.now(timezone.utc).isoformat()
        note = (doc['review_comment'] or '') + f'\n[{stamp}; user={user.id}] Замена / Ауыстыру: {reason}; {doc["original_file_name"]} → {original}'
        stored = StoredFile(object_key=key, stored_file_name=stored_name, original_file_name=original, content_type=mime[ext], file_size=len(content))
        try:
            await storage.save(content=content, object_key=key, content_type=mime[ext], metadata=None)
            await Repo.save(db, docs=docs, protocols=protocols, stored=stored, actor_id=user.id, note=note)
            await db.commit()
        except Exception:
            await db.rollback()
            try:
                committed = await Repo.referenced(db, key)
            except Exception:
                logger.exception('CORRECTION_COMMIT_UNKNOWN key=%s', key)
                raise HTTPException(503, 'Не удалось подтвердить сохранение. Обновите страницу перед повторной загрузкой / Сақталғанын растау мүмкін болмады. Бетті жаңартыңыз')
            if not committed:
                try:
                    await storage.delete(object_key=key)
                except Exception:
                    logger.exception('CORRECTION_ORPHAN_NEW key=%s', key)
                raise
            logger.warning('CORRECTION_COMMIT_ACK_LOST key=%s; committed reference verified', key)
        # Nothing after commit can delete the newly committed file.
        logger.info('DOCUMENT_CORRECTION %s', json.dumps(dict(actor=user.id, document_ids=[d['id'] for d in docs], protocol_ids=[p['id'] for p in protocols], reason=reason, old_keys=sorted(old_keys), new_key=key, at=stamp), ensure_ascii=False))
        failures = []
        for old in old_keys - {key}:
            try:
                if not await Repo.referenced(db, old):
                    await storage.delete(object_key=old)
            except Exception:
                logger.exception('CORRECTION_CLEANUP_FAILED key=%s', old)
                failures.append(old)
        return failures
