"""Own internal inbox. Reading never accepts or starts a task."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.modules.users.deps import get_current_user
from app.modules.users.models import User
from app.modules.planning.services.month_plan_notification_service import MonthPlanNotificationService as Service
from app.modules.planning.repositories.month_plan_notification_repo import SchoolMonthPlanNotificationRepo as Repo
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router = APIRouter(prefix='/notifications',tags=['internal-notifications'])

@router.get('/',name='internal_notifications_inbox',response_class=HTMLResponse)
async def inbox(request: Request, page: int = Query(1,ge=1,le=10000), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    Service.internal_identity(user)
    rows = await Repo.internal_inbox(db,user=user,page=page)
    return render(templates,request,'staff/notifications/inbox.html',dict(user=user,notices=[Service.internal_display(row) for row in rows[:20]],has_more=len(rows)>20,page=page))

@router.get('/unread-count',name='internal_notifications_count')
async def unread_count(db: AsyncSession = Depends(get_db),user: User = Depends(get_current_user)):
    Service.internal_identity(user)
    count = await Repo.internal_inbox(db,user=user,count_only=True)
    return JSONResponse(dict(unread=count),headers={'Cache-Control':'no-store'})

@router.get('/{notice_id}',name='internal_notification_detail',response_class=HTMLResponse)
async def detail(request: Request,notice_id: int,db: AsyncSession = Depends(get_db),user: User = Depends(get_current_user)):
    notice = await Service.internal_notice(db,user=user,notice_id=notice_id)
    return render(templates,request,'staff/notifications/detail.html',dict(user=user,notice=notice))

@router.post('/{notice_id}/read',name='internal_notification_read')
async def mark_read(request: Request,notice_id: int,db: AsyncSession = Depends(get_db),user: User = Depends(get_current_user)):
    Service.internal_identity(user)
    try:
        if not await Repo.internal_mark_read(db,user=user,notice_id=notice_id):
            raise HTTPException(404,'Уведомление не найдено / Хабарлама табылмады')
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return RedirectResponse(request.url_for('internal_notification_detail',notice_id=notice_id),status_code=303)
