"""Shared web flow for registration code issuance; routes retain their URLs."""
import logging
from uuid import uuid4
from fastapi import HTTPException
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from app.core.i18n import resolve_language
from app.modules.users.models import RegistrationCode
from app.modules.users.services.registration_code import RegistrationCodeService, LEVELS
from app.routers.web.helpers.issue_cache import cache_set, cache_get, cache_delete, cache_mark_saved
from app.routers.web.web_common import templates
from app.utils.pdf_code import generate_codes_pdf

logger = logging.getLogger(__name__)
URLS = {'L1': '/super/issue-l1', 'L2': '/l1/issue-l2', 'L3': '/l2/issue-l3'}
LISTS = {'L1': 'regions', 'L2': 'districts', 'L3': 'schools'}
TITLES = {'L1': 'Коды регистрации администраторов регионов (L1)',
          'L2': 'Коды регистрации администраторов районов (L2)',
          'L3': 'Коды регистрации администраторов школ (L3)'}


def _private(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


def _scope_id(user, level):
    if level == 'L3' and str(getattr(user.role, 'value', user.role)) == 'region_admin':
        return 'region:' + str(user.region_id)
    return user.region_id if level == 'L2' else user.district_id if level == 'L3' else None


def _check_user(user, level):
    allowed = ('district_admin', 'region_admin') if level == 'L3' else (getattr(LEVELS[level][0], 'value', LEVELS[level][0]),)
    if str(getattr(user.role, 'value', user.role)) not in allowed or not user.is_active or (level != 'L1' and (user.region_id if str(getattr(user.role, 'value', user.role)) == 'region_admin' else _scope_id(user, level)) is None):
        raise HTTPException(403, 'Нет права выдавать коды этого уровня')


def _base_url(user, level):
    if level == 'L3' and str(getattr(user.role, 'value', user.role)) == 'region_admin':
        return '/l1/issue-l3'
    return URLS[level]


async def page(request, db, user, level, *, error=None, status_code=200):
    _check_user(user, level)
    scope, rows = await RegistrationCodeService.get_catalog(db, user_id=user.id, level=level)
    context = dict(request=request, user=user, error=error, can_bootstrap_superuser=False)
    context[LISTS[level]] = rows
    if level == 'L2': context['region'] = scope
    if level == 'L3':
        regional = str(getattr(user.role, 'value', user.role)) == 'region_admin'
        context['district'] = None if regional else scope
        context['region'] = scope if regional else None
        context['issue_url'] = _base_url(user, level)
    return _private(templates.TemplateResponse('codes/issue_' + level.lower() + '.html', context, status_code=status_code))


async def submit(request, db, user, level, target_ids, quota_total):
    _check_user(user, level)
    user_id = user.id
    batch_id = str(uuid4())
    commit_started = False
    ids = []
    expected = {}
    scope_column = LEVELS[level][4]
    try:
        scope = await RegistrationCodeService.scope_name(db, actor={'role': user.role, 'region_id': user.region_id, 'district_id': user.district_id}, level=level)
        result = await RegistrationCodeService.issue_batch(db, issued_by_user_id=user_id, level=level,
                    target_ids=target_ids, quota_total=quota_total, expires_days=30)
        issued = [{scope_column + '_id': obj.region_id if level == 'L1' else obj.district_id if level == 'L2' else obj.school_id,
                   scope_column + '_name': name, 'raw_code': raw,
                   'quota_total': obj.quota_total, 'expires_at': obj.expires_at.strftime('%d.%m.%Y') if obj.expires_at else 'без срока'}
                  for raw, obj, name in result]
        ids = [obj.id for _, obj, _ in result]
        expected = {obj.id: obj.code_lookup_hash for _, obj, _ in result}
        # Persist result before the single database commit. A failed cache write
        # rolls back issuance. Result URLs are disclosed only after success.
        await run_in_threadpool(cache_set, batch_id, dict(owner_id=user_id, level=level,
            scope_id=_scope_id(user, level), scope_name=scope['name'] if scope else None, issued=issued))
        commit_started = True
        await db.commit()
    except BaseException as exc:
        await db.rollback()
        confirmed = False
        if commit_started:
            try:
                C = RegistrationCode.__table__
                found = dict((await db.execute(select(C.c.id, C.c.code_lookup_hash).where(C.c.id.in_(ids), C.c.issued_by_user_id == user_id))).all())
                confirmed = bool(expected) and found == expected
            except Exception:
                # Do not discard the only raw copy while the commit is uncertain.
                logger.exception('Code issuance commit outcome could not be confirmed')
                raise HTTPException(503, 'Не удалось подтвердить выдачу. Обновите страницу перед повторной выдачей.') from exc
        if not confirmed:
            await run_in_threadpool(cache_delete, batch_id)
            if isinstance(exc, (ValueError, IntegrityError, OSError)):
                await db.refresh(user)
                message = str(exc) if isinstance(exc, ValueError) else 'Не удалось сохранить выдачу кодов. Повторите действие.'
                return await page(request, db, user, level, error=message, status_code=400)
            raise
        logger.warning('Code issuance commit acknowledgement lost; committed batch confirmed')
    return _private(RedirectResponse(_base_url(user, level) + '/result/' + batch_id, status_code=303))


async def result(request, user, level, batch_id):
    _check_user(user, level)
    data = await run_in_threadpool(cache_get, batch_id, owner_id=user.id, level=level, scope_id=_scope_id(user, level), claim=True)
    if data is None:
        return _private(templates.TemplateResponse('codes/issue_result_expired.html', dict(request=request, user=user), status_code=410))
    # Never pass hidden raw codes to HTML after the first display.
    issued = data['issued'] if data['show_codes'] else [dict(row, raw_code='••••••••') for row in data['issued']]
    return _private(templates.TemplateResponse('codes/issue_' + level.lower() + '_result.html',
        dict(request=request, user=user, batch_id=batch_id, issue_url=_base_url(user, level), show_codes=data['show_codes'], saved=data['saved'], issued=issued, count=len(issued))))


async def pdf(request, user, level, batch_id):
    _check_user(user, level)
    scope_id = _scope_id(user, level)
    data = await run_in_threadpool(cache_get, batch_id, owner_id=user.id, level=level, scope_id=scope_id)
    if data is None: raise HTTPException(404, 'Batch not found or expired')
    arguments = dict(ui_language=resolve_language(request), title=TITLES[level], level_label=level, issued=data['issued'],
                     context_header={'L1': 'Регион', 'L2': 'Район', 'L3': 'Школа'}[level])
    if level != 'L1': arguments.update(scope_label='Область' if level == 'L2' or str(getattr(user.role, 'value', user.role)) == 'region_admin' else 'Район', scope_name=data['scope_name'])
    content = await run_in_threadpool(generate_codes_pdf, **arguments)
    await run_in_threadpool(cache_mark_saved, batch_id, owner_id=user.id, level=level, scope_id=scope_id)
    return _private(Response(content=content, media_type='application/pdf',
        headers={'Content-Disposition': 'attachment; filename="issue_' + level.lower() + '_' + str(uuid4()) + '.pdf"'}))
