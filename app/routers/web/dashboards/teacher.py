# app/routers/web/dashboards/teacher.py

from __future__ import annotations

from datetime import date

from fastapi import (
    APIRouter,
    Depends,
    Request,
)
from fastapi.responses import HTMLResponse

from app.modules.users.deps import (
    require_teacher_workspace,
)
from app.modules.users.models import User
from app.routers.web.dashboards.workspace_render import render_dashboard as render
from app.modules.users.enums import UserWorkspace
from app.routers.web.web_common import templates

router = APIRouter()


@router.get(
    "/dashboards/teacher",
    response_class=HTMLResponse,
    name="dashboard_teacher",
)
async def dashboard_teacher(
        request: Request,
        user: User = Depends(
            require_teacher_workspace
        ),
):
    """
    Стартовая панель учителя-предметника.
    """

    today = date.today()

    return render(
        templates,
        request,
        "dashboards/teacher.html",
        {
            "user": user,
            "today": today,
        },
        workspace=UserWorkspace.TEACHER,
    )
