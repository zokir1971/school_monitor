
from datetime import date

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.modules.staff.service_task import StaffTasksService
from app.routers.web.web_common import templates
from app.routers.web.helpers.render import render
from app.routers.web.jinja_filters import MONTH_NAMES_KZ


router = APIRouter(prefix="/staff/tasks", tags=["staff-tasks"])


@router.get("/", name="staff_tasks_page", response_class=HTMLResponse)
async def staff_tasks_page(
    request: Request,
    month: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    target_month = month or date.today().month

    if not (1 <= target_month <= 12):
        raise HTTPException(status_code=400, detail="month must be 1..12")

    tasks = await StaffTasksService.get_my_tasks_page(
        db,
        user=user,
        month=target_month,
    )

    return render(
        templates,
        request,
        "staff/school_staff_task.html",
        {
            "user": user,
            "tasks": tasks,
            "month": target_month,
            "MONTH_NAMES": MONTH_NAMES_KZ,
        },
    )
