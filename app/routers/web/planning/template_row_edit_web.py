"""Superuser-only editing of one row in a selected planning template."""
import logging
from typing import Literal
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.i18n import resolve_language
from app.modules.users.deps import get_db, require_roles
from app.modules.users.enums import UserRole
from app.modules.planning.enums import ReviewPlace
from app.modules.planning.services.template_row_edit_service import TemplateRowEditService as Service, FIELDS
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router = APIRouter(prefix='/builder')
logger = logging.getLogger(__name__)
Kind = Literal['rows4', 'rows11']
superuser = require_roles(UserRole.SUPERUSER)


def page(request, user, *, kind, row, template_id, direction_id, form=None, revision=None, error=None, status=200):
    values = {name: row.get(name) or '' for name in FIELDS[kind]}
    if kind == 'rows11':
        values['review_place'] = Service.review_value(row)
    if form is not None:
        values.update({name: form.get(name, values[name]) for name in FIELDS[kind] if isinstance(form.get(name, ''), str)})
    query = urlencode(dict(template_id=template_id, direction_id=direction_id))
    return render(templates, request, 'planning/super/template_row_edit.html', dict(
        user=user, ru=resolve_language(request, user) == 'ru', kind=kind, row=row,
        values=values, fields=FIELDS[kind], places=list(ReviewPlace),
        template_id=template_id, direction_id=direction_id,
        revision=revision if revision is not None else Service.revision(kind, row),
        back_url='/planning/super/builder?'+query+'#template-'+kind+'-'+str(row['id']),
        reopen_url=str(request.url_for('super_template_row_edit', table_kind=kind, row_id=row['id']))+'?'+query,
        error=error, conflict=status == 409,
    ), status_code=status)


@router.get('/{table_kind}/{row_id}/edit', name='super_template_row_edit', response_class=HTMLResponse)
async def edit_page(request: Request, table_kind: Kind, row_id: int,
                    template_id: int = Query(..., gt=0), direction_id: int = Query(..., gt=0),
                    db: AsyncSession = Depends(get_db), user=Depends(superuser)):
    row = await Service.load(db, kind=table_kind, row_id=row_id, template_id=template_id, direction_id=direction_id)
    return page(request, user, kind=table_kind, row=row, template_id=template_id, direction_id=direction_id)


@router.post('/{table_kind}/{row_id}/edit', name='super_template_row_update', response_class=HTMLResponse)
async def edit_submit(request: Request, table_kind: Kind, row_id: int,
                      template_id: int = Form(..., gt=0), direction_id: int = Form(..., gt=0),
                      revision: str = Form(...), db: AsyncSession = Depends(get_db), user=Depends(superuser)):
    form = await request.form()
    try:
        await Service.save(db, kind=table_kind, row_id=row_id, template_id=template_id, direction_id=direction_id, revision=revision, form=form)
        await db.commit()
    except HTTPException as exc:
        await db.rollback()
        if exc.status_code not in (400, 409):
            raise
        row = await Service.load(db, kind=table_kind, row_id=row_id, template_id=template_id, direction_id=direction_id)
        return page(request, user, kind=table_kind, row=row, template_id=template_id, direction_id=direction_id, form=form, revision=revision, error=exc.detail, status=exc.status_code)
    except Exception:
        await db.rollback()
        raise
    logger.info('TEMPLATE_ROW_EDIT actor=%s kind=%s row=%s template=%s direction=%s', user.id, table_kind, row_id, template_id, direction_id)
    query = urlencode(dict(template_id=template_id, direction_id=direction_id))
    return RedirectResponse('/planning/super/builder?'+query+'#template-'+table_kind+'-'+str(row_id), status_code=303)
