from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import uuid4

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException
from pdfminer.pdfdocument import PDFEncryptionError
from pdfminer.pdfparser import PDFSyntaxError
from pdfminer.psparser import PSEOF
from pdfplumber.utils.exceptions import PdfminerException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.core.storage import get_storage
from app.modules.assessment.helpers.learning_objective_pdf_import import extract_candidates, merge_languages, \
    pages_from_string
from app.modules.assessment.helpers.learning_objective_program_guard import verify_pdf_scope
from app.modules.assessment.helpers.learning_objective_table_import import extract_table, merge_table_languages
from app.modules.assessment.models_learning_objective_import import LearningObjectiveImportDraft
from app.modules.assessment.repositories.learning_objective_import_repo import LearningObjectiveImportRepo
from app.modules.assessment.services.learning_objective_import_service import validate_metadata, confirm_import
from app.modules.assessment.services.learning_objective_table_import_service import \
    validate_metadata as table_validate_metadata, confirm_table_import
from app.modules.users.deps import get_db, require_roles
from app.modules.users.enums import UserRole
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router = APIRouter(prefix='/learning-objectives', tags=['assessment.superuser.import'])
COOKIE = 'lo_import_csrf'
COOKIE_PATH = '/planning/super/learning-objectives'
MAX_PDF = 32 * 1024 * 1024
logger = logging.getLogger(__name__)
STORAGE_ERRORS = (OSError, BotoCoreError, ClientError)
PDF_ERRORS = (PDFSyntaxError, PDFEncryptionError, PSEOF, PdfminerException)


async def cleanup_uploaded_files(storage, object_keys: list[str]) -> None:
    """Clean up this attempt's UUID keys; log expected storage failures."""
    for object_key in object_keys:
        try:
            await storage.delete(object_key=object_key)
        except STORAGE_ERRORS:
            logger.exception('Не удалось удалить PDF после неуспешного импорта: %s', object_key)


async def refresh_user_after_rollback(db: AsyncSession, user: Any) -> None:
    await LearningObjectiveImportRepo.refresh_user_after_rollback(db, user)


async def subjects(db: AsyncSession) -> list[dict[str, Any]]:
    return await LearningObjectiveImportRepo.list_subjects(db)


def csrf(request, form):
    cookie = request.cookies.get(COOKIE, '')
    provided = str(form.get('csrf', ''))
    if len(cookie) != 64 or not secrets.compare_digest(cookie, provided):
        raise HTTPException(403, 'Обновите страницу и повторите отправку формы.')


def show(request, user, **context):
    return render(templates, request, 'super/assessment/learning_objective_import.html', {'user': user, **context})


@router.get('', name='super_learning_objective_import_page')
async def import_page(request: Request, db: AsyncSession = Depends(get_db),
                      user=Depends(require_roles(UserRole.SUPERUSER))):
    token = request.cookies.get(COOKIE, '')
    if len(token) != 64:
        token = secrets.token_hex(32)
    response = show(request, user, subjects=await subjects(db), csrf=token, form={})
    response.set_cookie(COOKIE, token, httponly=True, samesite='lax', secure=request.url.scheme == 'https',
                        path=COOKIE_PATH, max_age=86400)
    return response


async def read_pdf(upload, *, required):
    if upload is None or not getattr(upload, 'filename', ''):
        if required:
            raise ValueError('Загрузите казахский PDF.')
        return None
    try:
        content = await upload.read(MAX_PDF + 1)
    finally:
        await upload.close()
    if len(content) > MAX_PDF:
        raise ValueError('Размер PDF не должен превышать 32 МБ.')
    if not content.startswith(b'%PDF-'):
        raise ValueError('Загрузите PDF-файл.')
    return content


@router.post('/preview', name='super_learning_objective_import_preview')
async def preview(request: Request, db: AsyncSession = Depends(get_db),
                  user=Depends(require_roles(UserRole.SUPERUSER))):
    form = await request.form()
    csrf(request, form)
    saved: list[str] = []
    persisted = False
    storage = get_storage()
    try:
        meta = validate_metadata(dict(form))
        subject_name = await LearningObjectiveImportRepo.get_subject_name(db, meta['subject_id'])
        if subject_name is None:
            raise ValueError('Предмет не найден.')
        kz = await read_pdf(form.get('pdf_kz'), required=True)
        ru = await read_pdf(form.get('pdf_ru'), required=False)
        extracted: dict[str, Any] = {}
        warnings: list[str] = []
        payload: dict[str, Any] = {'metadata': meta}
        for language, content in (('kz', kz), ('ru', ru)):
            if content is None:
                extracted[language] = []
                continue
            pages = str(form.get('pages_' + language, ''))
            try:
                payload['program_binding_' + language] = await run_in_threadpool(verify_pdf_scope, content, pages=pages,
                                                                                 subject_name=subject_name, meta=meta)
                candidates, notes = await run_in_threadpool(extract_candidates, content, pages=pages,
                                                            grade_from=meta['grade_from'], grade_to=meta['grade_to'])
            except ValueError:
                raise
            except PDF_ERRORS as error:
                raise ValueError(
                    f'Не удалось прочитать PDF {language.upper()}. Проверьте файл и текстовый слой.') from error
            extracted[language] = candidates
            warnings.extend([language.upper() + ': ' + note for note in notes])
            payload['selected_pages_' + language] = sorted({p for c in candidates for p in c['pages']})
            import io, pdfplumber

            def all_selected(data, selection):
                with pdfplumber.open(io.BytesIO(data)) as pdf:
                    return pages_from_string(selection, total=len(pdf.pages))

            payload['selected_pages_' + language] = await run_in_threadpool(all_selected, content, pages)
            payload['sha256_' + language] = hashlib.sha256(content).hexdigest()
        payload['rows'] = merge_languages(extracted['kz'], extracted['ru'])
        payload['warnings'] = warnings
        token = str(uuid4())
        for language, content in (('kz', kz), ('ru', ru)):
            if content is None:
                continue
            key = f'learning-objective-imports/{user.id}/{token}/{language}.pdf'
            saved.append(key)
            await storage.save(content=content, object_key=key, content_type='application/pdf')
            payload['file_key_' + language] = key
        await LearningObjectiveImportRepo.create_draft(db, {'id': token, 'owner_user_id': user.id, 'payload': payload,
                                                            'expires_at': datetime.now(timezone.utc) + timedelta(
                                                                days=7)})
        await db.commit()
        persisted = True
        return RedirectResponse(request.url_for('super_learning_objective_import_draft', draft_id=token),
                                status_code=303)
    except ValueError as error:
        await db.rollback()
        await refresh_user_after_rollback(db, user)
        return show(request, user, subjects=await subjects(db), csrf=request.cookies.get(COOKIE, ''), form=dict(form),
                    error=str(error))
    except (OSError, BotoCoreError, ClientError, SQLAlchemyError):
        logger.exception('Ошибка хранилища или БД при подготовке PDF-импорта')
        await db.rollback()
        raise
    finally:
        if not persisted:
            await cleanup_uploaded_files(storage, saved)


async def owned_draft(db: AsyncSession, draft_id: str, user_id: int, *,
                      lock: bool = False) -> LearningObjectiveImportDraft:
    draft = await LearningObjectiveImportRepo.get_owned_draft(db, draft_id=draft_id, user_id=user_id, lock=lock)
    if draft is None:
        raise HTTPException(404, 'Предпросмотр не найден.')
    return draft


@router.get('/draft/{draft_id}', name='super_learning_objective_import_draft')
async def draft_page(request: Request, draft_id: str, db: AsyncSession = Depends(get_db),
                     user=Depends(require_roles(UserRole.SUPERUSER))):
    draft = await owned_draft(db, draft_id, user.id)
    return show(request, user, draft_id=draft.id, payload=cast(dict[str, Any], draft.payload),
                rows=cast(dict[str, Any], draft.payload)['rows'], result=draft.result,
                csrf=request.cookies.get(COOKIE, ''), expired=draft.expires_at <= datetime.now(timezone.utc))


@router.get('/draft/{draft_id}/file/{language}', name='super_learning_objective_import_file')
async def draft_file(draft_id: str, language: str, db: AsyncSession = Depends(get_db),
                     user=Depends(require_roles(UserRole.SUPERUSER))):
    if language not in ('kz', 'ru'):
        raise HTTPException(404)
    draft = await owned_draft(db, draft_id, user.id)
    payload = cast(dict[str, Any], draft.payload)
    key = payload.get('file_key_' + language)
    if not key:
        raise HTTPException(404, 'PDF не загружен.')
    storage = get_storage()
    if not await storage.exists(object_key=key):
        raise HTTPException(404, 'PDF не найден.')
    return RedirectResponse(await storage.get_download_url(object_key=key), status_code=307,
                            headers={'Cache-Control': 'no-store'})


@router.post('/draft/{draft_id}/confirm', name='super_learning_objective_import_confirm')
async def confirm(request: Request, draft_id: str, db: AsyncSession = Depends(get_db),
                  user=Depends(require_roles(UserRole.SUPERUSER))):
    form = await request.form()
    csrf(request, form)
    draft = await owned_draft(db, draft_id, user.id, lock=True)
    payload = cast(dict[str, Any], draft.payload)
    rows = payload['rows']
    try:
        if form.get('reviewed') != 'yes':
            raise ValueError('Подтвердите сверку целей с PDF.')
        raw = str(form.get('rows_json', ''))
        if len(raw.encode('utf-8')) > 900000:
            raise ValueError('Слишком большой предпросмотр. Разделите импорт на части.')
        try:
            rows = json.loads(raw)
        except (ValueError, TypeError):
            raise ValueError('Не удалось прочитать строки предпросмотра.') from None
        await confirm_import(db, draft=draft, rows=rows)
        await db.commit()
        return RedirectResponse(request.url_for('super_learning_objective_import_draft', draft_id=draft_id),
                                status_code=303)
    except (ValueError, IntegrityError) as error:
        await db.rollback()
        await refresh_user_after_rollback(db, user)
        message = str(error) if isinstance(error,
                                           ValueError) else 'Конфликт параллельного импорта. Обновите предпросмотр и ' \
                                                            'проверьте существующие коды.'
        return show(request, user, draft_id=draft_id, payload=payload,
                    rows=rows if isinstance(rows, list) else payload['rows'], csrf=request.cookies.get(COOKIE, ''),
                    error=message)


MAX_EXPORT = 10 * 1024 * 1024


async def table_cleanup_uploaded_files(storage, object_keys: list[str]) -> None:
    """Clean up this attempt's UUID keys; log expected storage failures."""
    for object_key in object_keys:
        try:
            await storage.delete(object_key=object_key)
        except STORAGE_ERRORS:
            logger.exception('Не удалось удалить XLS/XLSX после неуспешного импорта: %s', object_key)


async def table_refresh_user_after_rollback(db: AsyncSession, user: Any) -> None:
    await LearningObjectiveImportRepo.refresh_user_after_rollback(db, user)


async def table_subjects(db: AsyncSession) -> list[dict[str, Any]]:
    return await LearningObjectiveImportRepo.list_subjects(db)


def table_csrf(request, form):
    cookie = request.cookies.get(COOKIE, '')
    provided = str(form.get('csrf', ''))
    if len(cookie) != 64 or not secrets.compare_digest(cookie, provided):
        raise HTTPException(403, 'Обновите страницу и повторите отправку формы.')


def table_show(request, user, **context):
    return render(templates, request, 'super/assessment/learning_objective_table_import.html',
                  {'user': user, **context})


@router.get('/tables', name='super_learning_objective_table_import_page')
async def table_import_page(request: Request, db: AsyncSession = Depends(get_db),
                            user=Depends(require_roles(UserRole.SUPERUSER))):
    token = request.cookies.get(COOKIE, '')
    if len(token) != 64:
        token = secrets.token_hex(32)
    response = table_show(request, user, subjects=await table_subjects(db), csrf=token, form={})
    response.set_cookie(COOKIE, token, httponly=True, samesite='lax', secure=request.url.scheme == 'https',
                        path=COOKIE_PATH, max_age=86400)
    return response


async def table_read_export(upload, *, required):
    if upload is None or not getattr(upload, 'filename', ''):
        if required:
            raise ValueError('Загрузите казахскую выгрузку XLS/XLSX.')
        return None
    try:
        content = await upload.read(MAX_EXPORT + 1)
    finally:
        await upload.close()
    if len(content) > MAX_EXPORT:
        raise ValueError('Размер выгрузки не должен превышать 10 МБ.')
    return content


@router.post('/tables/preview', name='super_learning_objective_table_import_preview')
async def table_preview(request: Request, db: AsyncSession = Depends(get_db),
                        user=Depends(require_roles(UserRole.SUPERUSER))):
    form = await request.form()
    table_csrf(request, form)
    saved: list[str] = []
    persisted = False
    storage = get_storage()
    try:
        if form.get('source_confirmed') != 'yes':
            raise ValueError('Подтвердите предмет и источник выгрузки. Имя файла не подтверждает предмет.')
        raw_meta = dict(form)
        raw_meta['grade_from'] = raw_meta['grade_to'] = form.get('grade_level', '')
        meta = table_validate_metadata(raw_meta)
        subject_name = await LearningObjectiveImportRepo.get_subject_name(db, meta['subject_id'])
        if subject_name is None:
            raise ValueError('Предмет не найден.')
        kz = await table_read_export(form.get('export_kz'), required=True)
        ru = await table_read_export(form.get('export_ru'), required=False)
        extracted: dict[str, Any] = {}
        warnings: list[str] = []
        payload: dict[str, Any] = {'metadata': meta, 'import_kind': 'table_v1',
                                   'table_binding': {'subject_id': meta['subject_id'], 'subject_name': subject_name,
                                                     'confirmed': True}}
        for language, content in (('kz', kz), ('ru', ru)):
            if content is None:
                extracted[language] = []
                continue
            candidates, notes = await run_in_threadpool(extract_table, content, grade=meta['grade_from'])
            extracted[language] = candidates
            warnings.extend([language.upper() + ': ' + note for note in notes])
            payload['sha256_' + language] = hashlib.sha256(content).hexdigest()
            filename = str(form.get('export_' + language).filename).replace('\\', '/').rsplit('/', 1)[-1][:200]
            payload['filename_' + language] = filename
        digest = hashlib.sha256((payload['sha256_kz'] + payload.get('sha256_ru', '')).encode()).hexdigest()[:20]
        meta['document_key'] = f"{meta['document_key']}:{meta['subject_id']}:{meta['grade_from']}:{digest}"
        if len(meta['document_key']) > 150:
            raise ValueError('Сократите ключ источника до 100 символов.')
        payload['rows'] = merge_table_languages(extracted['kz'], extracted['ru'])
        payload['warnings'] = warnings
        token = str(uuid4())
        for language, content in (('kz', kz), ('ru', ru)):
            if content is None:
                continue
            suffix = 'xlsx' if content.startswith(b'PK') else 'xls'
            key = f'learning-objective-table-imports/{user.id}/{token}/{language}.{suffix}'
            saved.append(key)
            await storage.save(content=content, object_key=key, content_type='application/octet-stream')
            payload['file_key_' + language] = key
        await LearningObjectiveImportRepo.create_draft(db, {'id': token, 'owner_user_id': user.id, 'payload': payload,
                                                            'expires_at': datetime.now(timezone.utc) + timedelta(
                                                                days=7)})
        await db.commit()
        persisted = True
        return RedirectResponse(request.url_for('super_learning_objective_table_import_draft', draft_id=token),
                                status_code=303)
    except ValueError as error:
        await db.rollback()
        await table_refresh_user_after_rollback(db, user)
        return table_show(request, user, subjects=await table_subjects(db), csrf=request.cookies.get(COOKIE, ''),
                          form=dict(form), error=str(error))
    except (OSError, BotoCoreError, ClientError, SQLAlchemyError):
        logger.exception('Ошибка хранилища или БД при подготовке XLS/XLSX-импорта')
        await db.rollback()
        raise
    finally:
        if not persisted:
            await table_cleanup_uploaded_files(storage, saved)


async def table_owned_draft(db: AsyncSession, draft_id: str, user_id: int, *,
                            lock: bool = False) -> LearningObjectiveImportDraft:
    draft = await LearningObjectiveImportRepo.get_owned_draft(db, draft_id=draft_id, user_id=user_id, lock=lock)
    if draft is None:
        raise HTTPException(404, 'Предпросмотр не найден.')
    if draft.payload.get('import_kind') != 'table_v1':
        raise HTTPException(404, 'Табличный предпросмотр не найден.')
    return draft


@router.get('/tables/draft/{draft_id}', name='super_learning_objective_table_import_draft')
async def table_draft_page(request: Request, draft_id: str, db: AsyncSession = Depends(get_db),
                           user=Depends(require_roles(UserRole.SUPERUSER))):
    draft = await table_owned_draft(db, draft_id, user.id)
    return table_show(request, user, draft_id=draft.id, payload=cast(dict[str, Any], draft.payload),
                      rows=cast(dict[str, Any], draft.payload)['rows'], result=draft.result,
                      csrf=request.cookies.get(COOKIE, ''), expired=draft.expires_at <= datetime.now(timezone.utc))


@router.get('/tables/draft/{draft_id}/file/{language}', name='super_learning_objective_table_import_file')
async def table_draft_file(draft_id: str, language: str, db: AsyncSession = Depends(get_db),
                           user=Depends(require_roles(UserRole.SUPERUSER))):
    if language not in ('kz', 'ru'):
        raise HTTPException(404)
    draft = await table_owned_draft(db, draft_id, user.id)
    payload = cast(dict[str, Any], draft.payload)
    key = payload.get('file_key_' + language)
    if not key:
        raise HTTPException(404, 'Выгрузка не загружена.')
    storage = get_storage()
    if not await storage.exists(object_key=key):
        raise HTTPException(404, 'Выгрузка не найдена.')
    return RedirectResponse(await storage.get_download_url(object_key=key), status_code=307,
                            headers={'Cache-Control': 'no-store'})


@router.post('/tables/draft/{draft_id}/confirm', name='super_learning_objective_table_import_confirm')
async def table_confirm(request: Request, draft_id: str, db: AsyncSession = Depends(get_db),
                        user=Depends(require_roles(UserRole.SUPERUSER))):
    form = await request.form()
    table_csrf(request, form)
    draft = await table_owned_draft(db, draft_id, user.id, lock=True)
    payload = cast(dict[str, Any], draft.payload)
    rows = payload['rows']
    try:
        if form.get('reviewed') != 'yes':
            raise ValueError('Подтвердите сверку целей и четвертей с исходной выгрузкой.')
        raw = str(form.get('rows_json', ''))
        if len(raw.encode('utf-8')) > 900000:
            raise ValueError('Слишком большой предпросмотр. Разделите импорт на части.')
        try:
            rows = json.loads(raw)
        except (ValueError, TypeError):
            raise ValueError('Не удалось прочитать строки предпросмотра.') from None
        if payload.get('import_kind') != 'table_v1':
            raise ValueError('Это предпросмотр XLS/XLSX. Используйте страницу XLS/XLSX-импорта.')
        await confirm_table_import(db, draft=draft, rows=rows)
        await db.commit()
        return RedirectResponse(request.url_for('super_learning_objective_table_import_draft', draft_id=draft_id),
                                status_code=303)
    except (ValueError, IntegrityError) as error:
        await db.rollback()
        await table_refresh_user_after_rollback(db, user)
        message = str(error) if isinstance(error,
                                           ValueError) else 'Конфликт параллельного импорта. Обновите предпросмотр и ' \
                                                            'проверьте существующие коды.'
        return table_show(request, user, draft_id=draft_id, payload=payload,
                          rows=rows if isinstance(rows, list) else payload['rows'],
                          csrf=request.cookies.get(COOKIE, ''), error=message)


@router.get('/upload', name='super_learning_objective_upload_choice')
async def upload_choice(request: Request, user=Depends(require_roles(UserRole.SUPERUSER))):
    return render(templates, request, 'super/assessment/learning_objective_upload_choice.html', {'user': user})
