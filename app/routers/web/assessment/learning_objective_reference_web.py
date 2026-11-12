"""Saved-objective UI. Full prefix: include without another URL prefix."""
from __future__ import annotations
import json
import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import RedirectResponse
from app.modules.users.deps import get_db, require_roles
from app.modules.users.enums import UserRole
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates
from app.modules.assessment.repositories.learning_objective_reference_repo import LearningObjectiveReferenceRepo as Repo
from app.modules.assessment.services.learning_objective_reference_service import \
    LearningObjectiveReferenceService as Service, ObjectiveNotFound, ObjectiveEditConflict

router = APIRouter(prefix='/planning/super/learning-objectives/reference', tags=['assessment.superuser.reference'])
COOKIE = 'lo_reference_csrf'
COOKIE_PATH = '/planning/super/learning-objectives/reference'


def show_delete(request, user, subjects, *, scope=None, preview=None, error=None, deleted=None, status=200):
    token = request.cookies.get(COOKIE, '')
    if len(token) != 64:
        token = secrets.token_hex(32)
    response = render(templates, request, 'super/assessment/learning_objective_reference_delete.html',
                      dict(user=user, subjects=subjects, scope=scope or {}, preview=preview,
                           error=error, deleted=deleted, csrf=token))
    response.status_code = status
    response.headers['Cache-Control'] = 'no-store'
    response.set_cookie(COOKIE, token, httponly=True, samesite='lax', secure=request.url.scheme == 'https',
                        path=COOKIE_PATH, max_age=86400)
    return response


@router.get('/bulk-delete', name='super_learning_objective_delete_page')
async def delete_page(request: Request, subject_id: str = '', grade: str = '', instruction_language: str = '',
                      db: AsyncSession = Depends(get_db), user=Depends(require_roles(UserRole.SUPERUSER))):
    from app.modules.assessment.services.learning_objective_delete_service import (
        LearningObjectiveDeleteService as DeleteService, parse_scope,
    )
    scope, preview, error = {}, None, None
    if subject_id:
        try:
            scope = parse_scope(subject_id, grade, instruction_language)
            preview = await DeleteService.preview(db, scope)
        except ValueError as exc:
            error = str(exc)
    return show_delete(request, user, await Repo.subjects(db), scope=scope, preview=preview, error=error,
                       deleted=request.query_params.get('deleted'))


@router.post('/bulk-delete', name='super_learning_objective_delete_confirm')
async def delete_confirm(request: Request, db: AsyncSession = Depends(get_db),
                         user=Depends(require_roles(UserRole.SUPERUSER))):
    from sqlalchemy.exc import IntegrityError
    from app.modules.assessment.services.learning_objective_delete_service import (
        LearningObjectiveDeleteService as DeleteService, parse_scope,
    )
    form = await request.form()
    cookie = request.cookies.get(COOKIE, '')
    if len(cookie) != 64 or not secrets.compare_digest(cookie, str(form.get('csrf', ''))):
        raise HTTPException(403, 'Обновите страницу и повторите отправку.')
    scope = {}
    try:
        scope = parse_scope(form.get('subject_id'), form.get('grade'), form.get('instruction_language'))
        count = await DeleteService.remove(db, scope, expected=str(form.get('fingerprint', '')),
                                           confirmation=str(form.get('confirmation', '')))
        await db.commit()
    except (ValueError, IntegrityError) as exc:
        await db.rollback()
        await Repo.refresh_user(db, user)
        error = str(exc) if isinstance(exc, ValueError) else (
            'Удаление отменено из-за связанных данных. Ничего не удалено. Обновите предварительный просмотр.'
        )
        return show_delete(request, user, await Repo.subjects(db), scope=scope, error=error, status=409)
    return RedirectResponse(request.url_for('super_learning_objective_delete_page').include_query_params(
        deleted=str(count)), status_code=303)


def show(request, user, row, *, error=None, status=200, values=None):
    token = request.cookies.get(COOKIE, '')
    if len(token) != 64:
        token = secrets.token_hex(32)
    response = render(templates, request, 'super/assessment/learning_objective_reference_edit.html',
                      {'user': user, 'row': row, 'values': values or row, 'csrf': token, 'error': error})
    response.status_code = status
    response.set_cookie(COOKIE, token, httponly=True, samesite='lax', secure=request.url.scheme == 'https',
                        path=COOKIE_PATH, max_age=86400)
    return response


@router.get('', name='super_learning_objective_reference_list')
async def objective_list(request: Request, subject_id: str = '', grade: str = '', quarter: str = '', track: str = '',
                         state: str = 'all', q: str = '', page: int = 1, db: AsyncSession = Depends(get_db),
                         user=Depends(require_roles(UserRole.SUPERUSER))):
    try:
        result = await Service.page(db, subject_id=int(subject_id) if subject_id else None,
                                    grade=int(grade) if grade else None, quarter=int(quarter) if quarter else None,
                                    track=track, state=state, query=q, page=page)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return render(templates, request, 'super/assessment/learning_objective_reference_list.html',
                  {'user': user, 'page': result, 'subjects': await Repo.subjects(db),
                   'saved': request.query_params.get('saved') == '1'})


@router.get('/{objective_id}/edit', name='super_learning_objective_reference_edit')
async def edit_page(request: Request, objective_id: int, db: AsyncSession = Depends(get_db),
                    user=Depends(require_roles(UserRole.SUPERUSER))):
    try:
        row = await Service.get(db, objective_id)
    except ObjectiveNotFound as error:
        raise HTTPException(404, str(error)) from error
    if row.get('formulations'):
        return RedirectResponse(request.url_for('super_learning_objective_formulations_edit',
                                                objective_id=objective_id), status_code=303)
    return show(request, user, row)


@router.post('/{objective_id}/edit', name='super_learning_objective_reference_save')
async def save_page(request: Request, objective_id: int, db: AsyncSession = Depends(get_db),
                    user=Depends(require_roles(UserRole.SUPERUSER))):
    form = await request.form()
    cookie = request.cookies.get(COOKIE, '')
    if len(cookie) != 64 or not secrets.compare_digest(cookie, str(form.get('csrf', ''))):
        raise HTTPException(403, 'Обновите страницу и повторите отправку формы.')
    raw = None
    try:
        serialized = str(form.get('objective_json', ''))
        if len(serialized) > 200000:
            raise ValueError('Слишком большой текст цели.')
        try:
            raw = json.loads(serialized)
        except json.JSONDecodeError as error:
            raise ValueError('Неверная структура текста цели.') from error
        await Service.update(db, objective_id, raw=raw, expected_version=str(form.get('version', '')))
        await db.commit()
    except ObjectiveNotFound as error:
        await db.rollback()
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        await db.rollback()
        await Repo.refresh_user(db, user)
        try:
            row = await Service.get(db, objective_id)
        except ObjectiveNotFound as missing:
            raise HTTPException(404, str(missing)) from missing
        # Conflict: preserve the old version, so a retry cannot silently overwrite.
        if isinstance(error, ObjectiveEditConflict):
            row['version'] = str(form.get('version', ''))
        values = raw if isinstance(raw, dict) else None
        return show(request, user, row, error=str(error),
                    status=409 if isinstance(error, ObjectiveEditConflict) else 422, values=values)
    return RedirectResponse(request.url_for('super_learning_objective_reference_list').include_query_params(saved='1'),
                            status_code=303)


def show_formulations(request, user, row, rows, sources, *, error=None):
    token = request.cookies.get(COOKIE, '')
    if len(token) != 64:
        token = secrets.token_hex(32)
    response = render(templates, request, 'super/assessment/learning_objective_formulations.html',
                      {'user': user, 'row': row, 'rows': rows, 'sources': sources, 'csrf': token, 'error': error})
    response.set_cookie(COOKIE, token, httponly=True, samesite='lax', secure=request.url.scheme == 'https',
                        path=COOKIE_PATH, max_age=86400)
    return response


@router.get('/{objective_id}/formulations', name='super_learning_objective_formulations_edit')
async def formulations_page(request: Request, objective_id: int, db: AsyncSession = Depends(get_db),
                            user=Depends(require_roles(UserRole.SUPERUSER))):
    try:
        row, rows, sources = await Service.formulations_page(db, objective_id)
    except ObjectiveNotFound as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return show_formulations(request, user, row, rows, sources)


@router.post('/{objective_id}/formulations', name='super_learning_objective_formulations_save')
async def formulations_save(request: Request, objective_id: int, db: AsyncSession = Depends(get_db),
                            user=Depends(require_roles(UserRole.SUPERUSER))):
    form = await request.form()
    cookie = request.cookies.get(COOKIE, '')
    if len(cookie) != 64 or not secrets.compare_digest(cookie, str(form.get('csrf', ''))):
        raise HTTPException(403, 'Обновите страницу и повторите отправку.')
    rows = None
    try:
        serialized = str(form.get('rows_json', ''))
        if len(serialized.encode('utf-8')) > 900000:
            raise ValueError('Слишком большой текст.')
        try:
            rows = json.loads(serialized)
        except json.JSONDecodeError as error:
            raise ValueError('Неверная структура формулировок.') from error
        await Service.update_formulations(db, objective_id, rows=rows, expected_version=str(form.get('version', '')))
        await db.commit()
    except ObjectiveNotFound as error:
        await db.rollback()
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        await db.rollback()
        await Repo.refresh_user(db, user)
        row, original, sources = await Service.formulations_page(db, objective_id)
        if isinstance(error, ObjectiveEditConflict):
            row['version'] = str(form.get('version', ''))
        return show_formulations(request, user, row, rows if isinstance(rows, list) else original, sources,
                                 error=str(error))
    return RedirectResponse(request.url_for('super_learning_objective_reference_list').include_query_params(saved='1'),
                            status_code=303)
