from __future__ import annotations
from datetime import date
from pathlib import Path
import json
import os
import re
import secrets
import tempfile
import time
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
ROOT = Path(tempfile.gettempdir()) / 'school_monitor_nobd_previews'
TTL = 3600


def school(user):
    if not user.is_active or not user.school_id:
        raise HTTPException(403, 'Нужен активный администратор с привязкой к школе.')
    return int(user.school_id)


async def show(request, user, db: AsyncSession, **context):
    try:
        school_name = await NobdImportService.get_school_name(db, school_id=school(user))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    token = request.cookies.get(COOKIE, '')
    if len(token) != 64:
        token = secrets.token_hex(32)
    context.update(user=user, csrf=token, school_name=school_name, languages=LANGUAGES)
    response = render(templates, request, 'education/nobd_import.html', context)
    response.set_cookie(COOKIE, token, httponly=True, samesite='lax', secure=request.url.scheme == 'https',
                        path='/education/nobd-import', max_age=TTL)
    response.headers['Cache-Control'] = 'no-store'
    return response


def csrf(request, form):
    token = request.cookies.get(COOKIE, '')
    if len(token) != 64 or not secrets.compare_digest(token, str(form.get('csrf', ''))):
        raise HTTPException(403, 'Обновите страницу и повторите отправку.')


def year_value(value):
    try:
        year = int(value)
    except (ValueError, TypeError) as exc:
        raise ValueError('Укажите год начала учебного года.') from exc
    if not 2000 <= year <= 2100:
        raise ValueError('Год должен быть от 2000 до 2100.')
    return year


def cleanup():
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    for p in ROOT.glob('*.json'):
        try:
            if time.time() - p.stat().st_mtime > TTL:
                p.unlink(missing_ok=True)
        except FileNotFoundError:
            pass


def stage(payload):
    cleanup()
    token = secrets.token_hex(32)
    path = ROOT / (token + '.json')
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)
    return token


def load(token, user):
    cleanup()
    if not re.fullmatch(r'[0-9a-f]{64}', token):
        raise ValueError('Некорректный предпросмотр.')
    path = ROOT / (token + '.json')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise ValueError('Предпросмотр истёк или уже использован. Загрузите файл снова.') from exc
    if data['user_id'] != user.id or data['school_id'] != school(user):
        raise HTTPException(403, 'Предпросмотр принадлежит другому пользователю или школе.')
    return data, path


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
        token = stage(dict(user_id=user.id, school_id=school_id, year=year, data=data, fingerprint=fingerprint))
        return await show(request, user, db, year=year, preview=data, counters=counters, preview_token=token)
    except ValueError as exc:
        return await show(request, user, db, year=form.get('academic_year_start', ''), error=str(exc))


@router.post('/apply', name='school_nobd_import_apply')
async def apply(request: Request, db: AsyncSession = Depends(get_db),
                user=Depends(require_roles(UserRole.SCHOOL_ADMIN))):
    school_id = school(user)
    form = await request.form()
    csrf(request, form)
    payload = None
    token = str(form.get('preview_token', ''))
    try:
        payload, path = load(token, user)
        if form.get('confirm_school') != 'yes':
            raise ValueError('Подтвердите, что выгрузка относится к вашей школе.')
        tracks = {g['key']: str(form.get('track_' + g['key'], '')) for g in payload['data']['groups']}
        languages = {g['key']: str(form.get('language_' + g['key'], '')) for g in payload['data']['groups']}
        result = await NobdImportService.apply(db, school_id, payload['year'], payload['data'], tracks,
                                               form.get('confirm_tracks') == 'yes', payload['fingerprint'],
                                               languages=languages,
                                               confirm_languages=form.get('confirm_languages') == 'yes')
        await db.commit()
        path.unlink(missing_ok=True)
        return await show(request, user, db, year=payload['year'], result=result)
    except (ValueError, IntegrityError) as exc:
        await db.rollback()
        await CurriculumRepo.refresh_actor(db, user)
        error = str(exc) if isinstance(exc,
                                       ValueError) else 'Конфликт данных. Загрузите файл заново и проверьте ' \
                                                        'предпросмотр.'
        return await show(request, user, db, year=payload['year'] if payload else '', error=error,
                          preview=payload['data'] if payload else None, preview_token=token if payload else None)
