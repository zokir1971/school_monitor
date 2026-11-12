"""Superuser Subject reference pages; this router has its complete URL prefix."""
from __future__ import annotations
from dataclasses import asdict
import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import RedirectResponse
from app.modules.users.deps import get_db, require_roles
from app.modules.users.enums import UserRole
from app.modules.education.repositories.subject_reference_repo import SubjectReferenceRepo
from app.modules.education.schemas.subject_reference_dto import parse_subject_form
from app.modules.education.repositories.subject_category_repo import SubjectCategoryRepo
from app.modules.education.services.subject_category_service import SubjectCategoryService
from app.modules.education.helpers.curriculum_policy import POLICIES
from app.modules.education.services.subject_reference_service import SubjectReferenceService, SubjectNotFound
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router = APIRouter(prefix='/planning/super/education/subjects', tags=['education.superuser.subjects'])
COOKIE = 'subject_reference_csrf'
COOKIE_PATH = '/planning/super/education/subjects'


def check_csrf(request: Request, form) -> None:
    cookie, provided = request.cookies.get(COOKIE, ''), str(form.get('csrf', ''))
    if len(cookie) != 64 or not secrets.compare_digest(cookie, provided):
        raise HTTPException(403, 'Обновите страницу и повторите отправку формы.')


async def show_form(request: Request, user, db, *, form: dict, subject_id: int | None = None,
                    error: str | None = None, status_code: int = 200):
    token = request.cookies.get(COOKIE, '')
    if len(token) != 64:
        token = secrets.token_hex(32)
    response = render(templates, request, 'super/education/subjects/form.html',
                      {'user': user, 'form': form, 'subject_id': subject_id,
                       'editing': subject_id is not None, 'csrf': token, 'error': error,
                       'categories': await SubjectCategoryRepo.list_all(db), 'policies': POLICIES})
    response.status_code = status_code
    response.set_cookie(COOKIE, token, httponly=True, samesite='lax',
                        secure=request.url.scheme == 'https', path=COOKIE_PATH, max_age=86400)
    return response


@router.get('', name='super_subject_reference_list')
async def subject_list(request: Request, q: str = '', state: str = 'all', page: int = 1, category_id: str = '',
                       db: AsyncSession = Depends(get_db),
                       user=Depends(require_roles(UserRole.SUPERUSER))):
    try:
        selected_category = int(category_id) if category_id else None
        result = await SubjectReferenceService.list_page(db, query=q, state=state, page=page,
                                                         category_id=selected_category)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    previous_url = (request.url_for('super_subject_reference_list').include_query_params(
        q=result.query, state=result.state, page=result.page - 1,
        **({'category_id': result.category_id} if result.category_id is not None else {})) if result.page > 1 else None)
    next_url = (request.url_for(
        'super_subject_reference_list').include_query_params(
        q=result.query, state=result.state, page=result.page + 1, **({
            'category_id': result.category_id}
            if result.category_id is not None else {}))
                if result.page < result.pages else None)
    categories = await SubjectCategoryRepo.list_all(db)
    return render(templates, request, 'super/education/subjects/list.html',
                  {'user': user, 'page': result, 'categories': categories,
                   'category_by_id': {c['id']: c for c in categories}, 'previous_url': previous_url,
                   'next_url': next_url, 'saved': request.query_params.get('saved') == '1',
                   'deleted': request.query_params.get('deleted') == '1'})


@router.get('/create', name='super_subject_reference_create_page')
async def create_page(request: Request, db: AsyncSession = Depends(get_db),
                      user=Depends(require_roles(UserRole.SUPERUSER))):
    return await show_form(request, user, db,
                           form={'sort_order': '100', 'is_active': 'yes', 'curriculum_role': 'general'})


@router.post('/create', name='super_subject_reference_create')
async def create_subject(request: Request, db: AsyncSession = Depends(get_db),
                         user=Depends(require_roles(UserRole.SUPERUSER))):
    form = await request.form()
    check_csrf(request, form)
    try:
        data = parse_subject_form(form)
        await SubjectReferenceService.create(db, data)
        await db.commit()
    except ValueError as error:
        await db.rollback()
        await SubjectReferenceRepo.refresh_user_after_rollback(db, user)
        return await show_form(request, user, db, form=dict(form), error=str(error), status_code=422)
    except IntegrityError as error:
        await db.rollback()
        if not SubjectReferenceRepo.is_code_conflict(error):
            raise
        await SubjectReferenceRepo.refresh_user_after_rollback(db, user)
        return await show_form(request, user, db, form=dict(form), status_code=409,
                               error='Предмет с таким кодом уже создан. Проверьте справочник.')
    return RedirectResponse(request.url_for('super_subject_reference_list').include_query_params(saved='1'),
                            status_code=303)


@router.get('/categories', name='super_subject_categories')
async def categories_page(request: Request, edit: int | None = None, db: AsyncSession = Depends(get_db),
                          user=Depends(require_roles(UserRole.SUPERUSER))):
    categories = await SubjectCategoryRepo.list_all(db)
    selected = next((c for c in categories if c['id'] == edit), None)
    if edit is not None and selected is None:
        raise HTTPException(404, 'Категория не найдена.')
    return show_categories(request, user, categories, selected or {})


def show_categories(request, user, categories, form, error=None, status=200):
    token = request.cookies.get(COOKIE, '')
    if len(token) != 64:
        token = secrets.token_hex(32)
    response = render(templates, request, 'super/education/subjects/categories.html',
                      dict(user=user, categories=categories, form=form, csrf=token, error=error))
    response.status_code = status
    response.set_cookie(COOKIE, token, httponly=True, samesite='lax',
                        secure=request.url.scheme == 'https', path=COOKIE_PATH, max_age=86400)
    return response


@router.post('/categories/save', name='super_subject_category_save')
async def save_category(request: Request, db: AsyncSession = Depends(get_db),
                        user=Depends(require_roles(UserRole.SUPERUSER))):
    form = await request.form()
    check_csrf(request, form)
    try:
        category_id = int(form['id']) if form.get('id') else None
        if category_id is not None and category_id <= 0:
            raise ValueError('Некорректная категория.')
        await SubjectCategoryService.save(db, form, category_id)
        await db.commit()
    except (ValueError, IntegrityError) as exc:
        await db.rollback()
        await SubjectReferenceRepo.refresh_user_after_rollback(db, user)
        categories = await SubjectCategoryRepo.list_all(db)
        message = str(exc) if isinstance(exc, ValueError) else 'Категория с таким кодом уже существует.'
        return show_categories(request, user, categories, dict(form), message, 422)
    return RedirectResponse(request.url_for('super_subject_categories'), status_code=303)


def show_delete(request, user, preview, *, error=None, status=200):
    token = request.cookies.get(COOKIE, '')
    if len(token) != 64:
        token = secrets.token_hex(32)
    response = render(templates, request, 'super/education/subjects/delete.html',
                      dict(user=user, preview=preview, csrf=token, error=error))
    response.status_code = status
    response.headers['Cache-Control'] = 'no-store'
    response.set_cookie(COOKIE, token, httponly=True, samesite='lax',
                        secure=request.url.scheme == 'https', path=COOKIE_PATH, max_age=86400)
    return response


@router.get('/{subject_id}/delete', name='super_subject_reference_delete_page')
async def delete_page(request: Request, subject_id: int, db: AsyncSession = Depends(get_db),
                      user=Depends(require_roles(UserRole.SUPERUSER))):
    from app.modules.education.services.subject_delete_service import SubjectDeleteService
    try:
        preview = await SubjectDeleteService.preview(db, subject_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return show_delete(request, user, preview)


@router.post('/{subject_id}/delete', name='super_subject_reference_delete')
async def delete_subject(request: Request, subject_id: int, db: AsyncSession = Depends(get_db),
                         user=Depends(require_roles(UserRole.SUPERUSER))):
    from app.modules.education.services.subject_delete_service import SubjectDeleteService
    form = await request.form()
    check_csrf(request, form)
    try:
        await SubjectDeleteService.remove(db, subject_id, expected=str(form.get('fingerprint', '')),
                                          confirmation=str(form.get('confirmation', '')))
        await db.commit()
    except (ValueError, IntegrityError) as exc:
        await db.rollback()
        await SubjectReferenceRepo.refresh_user_after_rollback(db, user)
        try:
            preview = await SubjectDeleteService.preview(db, subject_id)
        except ValueError as missing:
            raise HTTPException(404, str(missing)) from missing
        message = str(exc) if isinstance(exc, ValueError) else (
            'Предмет связан с другими данными. Удаление отменено, связанные записи сохранены.'
        )
        return show_delete(request, user, preview, error=message, status=409)
    return RedirectResponse(request.url_for('super_subject_reference_list').include_query_params(deleted='1'),
                            status_code=303)


@router.get('/{subject_id}/edit', name='super_subject_reference_edit_page')
async def edit_page(request: Request, subject_id: int, db: AsyncSession = Depends(get_db),
                    user=Depends(require_roles(UserRole.SUPERUSER))):
    try:
        subject = await SubjectReferenceService.get(db, subject_id)
    except SubjectNotFound as error:
        raise HTTPException(404, str(error)) from error
    form = asdict(subject)
    form['name_ru'] = subject.name_ru or ''
    form['is_active'] = 'yes' if subject.is_active else ''
    return await show_form(request, user, db, form=form, subject_id=subject_id)


@router.post('/{subject_id}/edit', name='super_subject_reference_update')
async def update_subject(request: Request, subject_id: int, db: AsyncSession = Depends(get_db),
                         user=Depends(require_roles(UserRole.SUPERUSER))):
    form = await request.form()
    check_csrf(request, form)
    try:
        data = parse_subject_form(form, editing=True)
        await SubjectReferenceService.update(db, subject_id, data)
        await db.commit()
    except SubjectNotFound as error:
        await db.rollback()
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        await db.rollback()
        await SubjectReferenceRepo.refresh_user_after_rollback(db, user)
        return await show_form(request, user, db, form=dict(form), subject_id=subject_id,
                               error=str(error), status_code=422)
    return RedirectResponse(request.url_for('super_subject_reference_list').include_query_params(saved='1'),
                            status_code=303)
