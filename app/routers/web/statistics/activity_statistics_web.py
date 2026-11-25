from urllib.parse import urlencode
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.modules.users.deps import get_current_user
from app.modules.statistics.activity_service import ActivityStatisticsService
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router = APIRouter(prefix='/statistics', tags=['Statistics.Activity.Web'])


@router.get('/activity', name='school_activity_statistics_page', response_class=HTMLResponse)
async def school_activity_statistics_page(request: Request, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    # Exact role: require_roles also permits SUPERUSER implicitly on other pages.
    if getattr(user.role, 'value', user.role) != 'superuser' or not user.is_active:
        raise HTTPException(403, 'Нет доступа / Қолжетімділік жоқ')
    data = await ActivityStatisticsService.page(db, user, request.query_params)
    filters = {key: data[key] for key in ('period', 'start', 'end', 'governance','region_id', 'district_id', 'view', 'sort', 'order', 'attention', 'q')}

    def link(**changes):
        values = dict(filters, page=1)
        values.update(changes)
        return '/statistics/activity?' + urlencode({k: v for k, v in values.items() if v is not None and v != ''})

    from datetime import timezone
    from app.modules.statistics.activity_tracking import LOCAL_TZ
    def local_stamp(value):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(LOCAL_TZ).strftime('%d.%m.%Y %H:%M')

    response = render(templates, request, 'statistics/activity.html', dict(user=user, **data, link=link, local_stamp=local_stamp))
    response.headers['Cache-Control'] = 'no-store'
    return response
