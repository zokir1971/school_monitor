from __future__ import annotations
from datetime import date
from urllib.parse import urlencode
from fastapi.responses import RedirectResponse
from app.core import import_guard275 as guard
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.db.session import get_db
from app.modules.education.repositories.curriculum_repo import CurriculumRepo
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.education.helpers.nobd_parser import parse_nobd, MAX_BYTES
from app.modules.education.helpers.subgroup_policy import LANGUAGES
from app.modules.education.services.nobd_import_service import NobdImportService
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router = APIRouter(prefix='/education/nobd-import', tags=['education-nobd'])
COOKIE = 'nobd_import_csrf'
TTL = guard.TTL


def school(user):
    if not user.is_active or not user.school_id:
        raise HTTPException(403, 'Нужен активный администратор с привязкой к школе.')
    return int(user.school_id)


async def show(request, user, db: AsyncSession, **context):
    try:
        school_name = await NobdImportService.get_school_name(db, school_id=school(user))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    token = guard.csrf_token(request, COOKIE)
    context.update(user=user, csrf=token, school_name=school_name, school_id=school(user), languages=LANGUAGES)
    if context.get('counters') and context.get('preview'):
        counts = context['counters']
        context['import_stats'] = guard.summary(len(context['preview']['rows']), counts['new_students'],
                                                 counts['existing_students'])
    response = render(templates, request, 'education/nobd_import.html', context)
    response.set_cookie(COOKIE, token, httponly=True, samesite='lax', secure=request.url.scheme == 'https',
                        path='/education/nobd-import', max_age=TTL)
    response.headers['Cache-Control'] = 'no-store'
    return response


def csrf(request, form):
    guard.check_csrf(request, form, COOKIE)


def year_value(value):
    try:
        year = int(value)
    except (ValueError, TypeError) as exc:
        raise ValueError('Укажите год начала учебного года.') from exc
    if not 2000 <= year <= 2100:
        raise ValueError('Год должен быть от 2000 до 2100.')
    return year


def stage(payload):
    return guard.stage(payload, 'students')


def load(token, user):
    return guard.load(token, user, 'students')


@router.get('', name='school_nobd_import_page')
async def page(request: Request, db: AsyncSession = Depends(get_db),
               user=Depends(require_roles(UserRole.SCHOOL_ADMIN))):
    school(user)
    today = date.today()
    return await show(request, user, db, year=today.year if today.month >= 9 else today.year - 1)


@router.post('/preview', name='school_nobd_import_preview')
async def preview(request: Request, db: AsyncSession = Depends(get_db),
                  user=Depends(require_roles(UserRole.SCHOOL_ADMIN))):
    school_id = school(user)
    form = await request.form()
    csrf(request, form)
    try:
        year = year_value(form.get('academic_year_start'))
        upload = form.get('file')
        if not hasattr(upload, 'read'):
            raise ValueError('Выберите CSV-файл НОБД.')
        raw = await upload.read(MAX_BYTES + 1)
        await upload.close()
        data = parse_nobd(raw)
        if data['errors']:
            return await show(request, user, db, year=year, preview=data)
        counters, fingerprint, *_ = await NobdImportService.snapshot(db, school_id, year, data)
        token = stage(dict(user_id=user.id, school_id=school_id, year=year, data=data, fingerprint=fingerprint, counters=counters,
                           stats=guard.summary(len(data['rows']), counters['new_students'], counters['existing_students'])))
        return RedirectResponse("/education/nobd-import/preview?" + urlencode({"token": token}), status_code=303)
    except ValueError as exc:
        return await show(request, user, db, year=form.get('academic_year_start', ''), error=str(exc))


@router.get('/preview', name='school_nobd_import_preview_page')
async def preview_page(request: Request, db: AsyncSession = Depends(get_db),
                       user=Depends(require_roles(UserRole.SCHOOL_ADMIN))):
    school(user)
    try:
        token = request.query_params.get('token', '')
        payload, _ = load(token, user)
        return await show(request, user, db, year=payload['year'], preview=payload['data'],
                          counters=payload['counters'], preview_token=token)
    except ValueError as exc:
        return await show(request, user, db, error=str(exc))


@router.post('/apply', name='school_nobd_import_apply')
async def apply(request: Request, db: AsyncSession = Depends(get_db),
                user=Depends(require_roles(UserRole.SCHOOL_ADMIN))):
    school_id = school(user)
    form = await request.form()
    csrf(request, form)
    payload = None
    claimed = None
    token = str(form.get('preview_token', ''))
    try:
        payload, path = load(token, user)
        guard.confirm(form, school_id, payload['stats'])
        tracks = {g['key']: str(form.get('track_' + g['key'], '')) for g in payload['data']['groups']}
        languages = {g['key']: str(form.get('language_' + g['key'], '')) for g in payload['data']['groups']}
        claimed = guard.claim(path)
        result = await NobdImportService.apply(db, school_id, payload['year'], payload['data'], tracks,
                                               form.get('confirm_tracks') == 'yes', payload['fingerprint'],
                                               languages=languages,
                                               confirm_languages=form.get('confirm_languages') == 'yes')
        await db.commit()
        return await show(request, user, db, year=payload['year'], result=result)
    except (ValueError, IntegrityError) as exc:
        await db.rollback()
        await CurriculumRepo.refresh_actor(db, user)
        error = str(exc) if isinstance(exc,
                                       ValueError) else 'Конфликт данных. Загрузите файл заново и проверьте ' \
                                                        'предпросмотр.'
        return await show(request, user, db, year=payload['year'] if payload else '', error=error,
                          preview=payload['data'] if payload else None,
                          import_stats=payload['stats'] if payload else None,
                          preview_token=token if payload and claimed is None else None)
    except Exception:
        await db.rollback()
        raise
    finally:
        if claimed:
            claimed.unlink(missing_ok=True)
