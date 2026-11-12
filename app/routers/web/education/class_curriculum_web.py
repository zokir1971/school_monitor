from datetime import date
from time import perf_counter
import secrets
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from starlette.responses import RedirectResponse
from app.db.session import get_db
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.education.services.class_curriculum_service import ClassCurriculumService as Service
from app.modules.education.repositories.curriculum_repo import CurriculumRepo
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router = APIRouter(tags=['education-curriculum'])
COOKIE = 'class_curriculum_csrf'


def school_id(user):
    if not user.is_active or not user.school_id:
        raise HTTPException(403, 'Нужна привязка к школе.')
    return int(user.school_id)


def current_year():
    today = date.today()
    return today.year if today.month >= 9 else today.year - 1


def show(request, user, template, context):
    token = request.cookies.get(COOKIE, '')
    if len(token) != 64:
        token = secrets.token_hex(32)
    response = render(templates, request, template, dict(context, user=user, csrf=token))
    response.set_cookie(COOKIE, token, httponly=True, samesite='lax', secure=request.url.scheme == 'https', path='/',
                        max_age=86400)
    response.headers['Cache-Control'] = 'no-store'
    return response


def check_csrf(request, form):
    token = request.cookies.get(COOKIE, '')
    if len(token) != 64 or not secrets.compare_digest(token, str(form.get('csrf', ''))):
        raise HTTPException(403, 'Обновите страницу и повторите отправку.')


def number(form, key, default=None):
    value = form.get(key)
    if value in (None, '') and default is not None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'Проверьте поле {key}.') from exc


async def school_view(request, user, db, year, error=None, notice=None):
    started=perf_counter()
    try:
        context = await Service.page(db, school_id(user), year)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    # POST /update can render this page on success or validation failure.
    # The language switch always returns to the reader, preserving the chosen year.
    query=[(k,v) for k,v in request.query_params.multi_items() if k!='academic_year_start']
    query.append(('academic_year_start',str(year)))
    read_url=request.url_for('school_class_subjects_page').path+'?'+urlencode(query)
    loaded=perf_counter()
    response=show(request, user, 'education/class_curriculum.html',
                dict(context, error=error, notice=notice, ui_return_url=read_url,
                     lazy_teacher_choices=request.query_params.get('teacher_choices')!='full'))
    rendered=perf_counter()
    response.headers['Server-Timing']=f'curriculum_data;dur={(loaded-started)*1000:.2f}, curriculum_render;dur={(rendered-loaded)*1000:.2f}'
    return response


@router.get('/planning/super/education/curriculum', name='super_curriculum_page')
async def reference_page(request: Request, db: AsyncSession = Depends(get_db),
                         user=Depends(require_roles(UserRole.SUPERUSER))):
    context = await Service.reference_page(db)
    return show(request, user, 'education/curriculum_reference.html',
                dict(context, notice=request.query_params.get('notice')))


@router.post('/planning/super/education/curriculum/save', name='super_curriculum_save')
async def reference_save(request: Request, db: AsyncSession = Depends(get_db),
                         user=Depends(require_roles(UserRole.SUPERUSER))):
    form = await request.form()
    check_csrf(request, form)
    try:
        action = form.get('action')
        if action == 'profile':
            await Service.save_profile(db, str(form.get('code', '')), str(form.get('name', '')))
        elif action == 'delete_rule':
            await Service.delete_rule(db, number(form, 'rule_id'))
        elif action == 'deactivate':
            await Service.deactivate_rule(db, number(form, 'rule_id'))
        elif action == 'edit_rule':
            if form.get('split_mode') not in ('whole', 'threshold'):
                raise ValueError('Выберите режим деления.')
            if number(form, 'grade_from') != number(form, 'grade_to'):
                raise ValueError('Редактируется одна параллель; значения начала и конца должны совпадать.')
            await Service.edit_rule(db, number(form, 'rule_id'), str(form.get('language', '')),
                                    number(form, 'grade_from'), str(form.get('track', '')), number(form, 'subject_id'),
                                    number(form, 'profile_id', 0) or None,
                                    number(form, 'split_threshold') if form.get('split_mode') == 'threshold' else None,
                                    form.get('is_active') == 'yes')
        elif action == 'rule':
            if form.get('split_mode') not in ('whole', 'threshold'):
                raise ValueError('Выберите режим деления.')
            await Service.save_rule_set(db, str(form.get('language', '')), number(form, 'grade_from'),
                                        number(form, 'grade_to'), str(form.get('track', '')),
                                        number(form, 'subject_id'),
                                        number(form, 'profile_id', 0) or None,
                                        split_threshold=number(form, 'split_threshold') if form.get(
                                            'split_mode') == 'threshold' else None)
        else:
            raise ValueError('Неизвестное действие.')
        await db.commit()
    except (ValueError, IntegrityError) as exc:
        await db.rollback()
        await CurriculumRepo.refresh_actor(db, user)
        error = str(exc) if isinstance(exc, ValueError) else 'Конфликт записи. Обновите страницу и повторите.'
        context = await Service.reference_page(db)
        return show(request, user, 'education/curriculum_reference.html', dict(context, error=error))
    return RedirectResponse(request.url_for('super_curriculum_page').include_query_params(
        notice='Сохранено. Для существующих классов выполните обновление предметов.'), 303)


@router.get('/education/class-subjects', name='school_class_subjects_page')
async def school_page(request: Request, academic_year_start: int | None = None, db: AsyncSession = Depends(get_db),
                      user=Depends(require_roles(UserRole.SCHOOL_ADMIN))):
    return await school_view(request, user, db,
                             academic_year_start if academic_year_start is not None else current_year())


@router.post('/education/class-subjects/update', name='school_class_subjects_update')
async def school_update(request: Request, db: AsyncSession = Depends(get_db),
                        user=Depends(require_roles(UserRole.SCHOOL_ADMIN))):
    form = await request.form()
    check_csrf(request, form)
    sid = school_id(user)
    year = current_year()
    try:
        year = number(form, 'academic_year_start')
        action = form.get('action')
        if action == 'language':
            c = await Service.set_language(db, sid, number(form, 'class_id'), str(form.get('language', '')))
            result = c
        elif action == 'sync':
            result = await Service.sync(db, sid, year)
        elif action == 'assign':
            await Service.assign(db, sid, number(form, 'offer_id'), number(form, 'subgroup_id', 0) or None,
                                 number(form, 'staff_id'))
            result = dict(warnings=[])
        else:
            raise ValueError('Неизвестное действие.')
        await db.commit()
        notice = 'Сохранено.'
        if result['warnings']:
            notice += ' ' + ' '.join(result['warnings'])
        return await school_view(request, user, db, year, notice=notice)
    except (ValueError, IntegrityError) as exc:
        await db.rollback()
        await CurriculumRepo.refresh_actor(db, user)
        error = str(exc) if isinstance(exc, ValueError) else 'Конфликт данных. Обновите страницу и повторите.'
        if not 2000 <= year <= 2100:
            year = current_year()
        return await school_view(request, user, db, year, error=error)
