# app/routers/web/dashboards/school_staff.py

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.web_common import templates

router = APIRouter()


@router.get(
    "/dashboards/staff_school",
    response_class=HTMLResponse,
    name="dashboard_staff_school",
)
async def dashboard_staff_school(
    request: Request,
    user: User = Depends(require_roles(UserRole.SCHOOL_STAFF)),
):
    return templates.TemplateResponse(
        request,
        "dashboards/school_staff.html",
        {
            "request": request,
            "user": user,
        },
    )