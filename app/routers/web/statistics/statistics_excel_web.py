from datetime import datetime
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.modules.users.deps import get_current_user
from app.core.i18n import resolve_language
from app.modules.statistics.excel_export import collect, workbook
from app.modules.statistics.activity_tracking import LOCAL_TZ
from app.core.planning_profile import measure_export_phase, record_excel_context

router = APIRouter(prefix='/statistics', tags=['Statistics.Excel'])


async def export_response(request, db, user, activity):
    role = getattr(user.role, 'value', user.role)
    allowed = ('superuser',) if activity else ('superuser', 'region_admin', 'district_admin')
    if not user.is_active or role not in allowed:
        raise HTTPException(403, 'Нет доступа / Қолжетімділік жоқ')
    language = resolve_language(request, user)
    with measure_export_phase('excel_data'):
        data, sheets = await collect(db, user, request.query_params, activity=activity)
    selection = {key: data.get(key) for key in ('year','month','region_id','district_id','school_id','direction_id','start','end','q','sort','order','attention')}
    selection.update(role=role, language=language, activity=activity,
                     scope={key: data.get('scope', {}).get(key) for key in ('kind','region_id','district_id')})
    record_excel_context(role, language, 'activity' if activity else 'wshk', selection, sheets)
    with measure_export_phase('excel_build'):
        content = await run_in_threadpool(workbook, data, sheets, language, activity=activity)
    name = ('school_activity_' if activity else 'wshk_statistics_') + datetime.now(LOCAL_TZ).strftime('%Y%m%d_%H%M%S') + '.xlsx'
    return Response(content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename="{name}"', 'Cache-Control': 'no-store',
                             'X-Content-Type-Options': 'nosniff'})


@router.get('/territory/excel', name='territorial_statistics_excel')
async def territorial_statistics_excel(request: Request, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    return await export_response(request, db, user, False)


@router.get('/activity/excel', name='activity_statistics_excel')
async def activity_statistics_excel(request: Request, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    return await export_response(request, db, user, True)
