from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.modules.reports.services.document_correction_service import DocumentCorrectionService as Service
from app.routers.web.web_common import templates

router = APIRouter()

@router.get('/corrections/{month_item_id}', name='task_document_correction_page')
async def correction_page(request: Request, month_item_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN, UserRole.SCHOOL_STAFF))):
    documents = await Service.page(db, user=user, month_item_id=month_item_id)
    return templates.TemplateResponse('staff/reports/document_correction.html', dict(request=request, user=user, documents=documents, month_item_id=month_item_id))

@router.post('/corrections/{month_item_id}', name='task_document_correction_save')
async def correction_save(request: Request, month_item_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN, UserRole.SCHOOL_STAFF))):
    form = await request.form()
    upload = form.get('replacement_file')
    query = {}
    try:
        if upload is None or not getattr(upload, 'filename', None):
            raise HTTPException(400, 'Выберите файл / Файлды таңдаңыз')
        try:
            document_id = int(form.get('document_id') or '')
        except (TypeError, ValueError):
            raise HTTPException(400, 'Выберите документ / Құжатты таңдаңыз')
        failures = await Service.replace(db, user=user, month_item_id=month_item_id, document_id=document_id, expected_key=str(form.get('expected_key') or ''), reason=form.get('reason'), upload=upload)
        query['success'] = 'Файл заменён / Файл ауыстырылды'
        if failures:
            query['warning'] = 'Новый файл сохранён, старый файл не удалось удалить. Сообщите администратору / Жаңа файл сақталды, ескі файл жойылмады. Әкімшіге хабарлаңыз'
    except HTTPException as exc:
        await db.rollback()
        if exc.status_code in (403, 404):
            raise
        query['error'] = str(exc.detail)
    except Exception:
        await db.rollback()
        import logging
        logging.getLogger(__name__).exception('Document correction failed')
        query['error'] = 'Не удалось заменить файл. Прежний документ сохранён / Файлды ауыстыру мүмкін болмады. Алдыңғы құжат сақталды'
    finally:
        if upload is not None and hasattr(upload, 'close'):
            await upload.close()
    return RedirectResponse(str(request.url_for('task_document_correction_page', month_item_id=month_item_id)) + '?' + urlencode(query), status_code=303)
