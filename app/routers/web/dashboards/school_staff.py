# app/routers/web/dashboards/school_staff.py
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.modules.users.deps import require_staff_workspace
from app.modules.users.models import User
from app.routers.web.dashboards.workspace_render import render_dashboard as render
from app.modules.users.enums import UserWorkspace
from app.routers.web.web_common import templates

router = APIRouter()


@router.get(
    "/dashboards/staff_school",
    response_class=HTMLResponse,
    name="dashboard_staff_school",
)
async def dashboard_staff_school(
    request: Request,
        user: User = Depends(
            require_staff_workspace
        ),
):
    today = date.today()
    return render(
        templates,
        request,
        "dashboards/school_staff.html",
        {
            "request": request,
            "user": user,
            "today": today,
        },
        workspace=UserWorkspace.STAFF,
    )
