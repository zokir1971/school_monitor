# app/routers/web/dashboards/common.py

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette import status

from app.modules.users.deps import get_current_user, require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.web_common import templates

router = APIRouter()


@router.get("/dashboards", name="dashboard_redirect")
async def dashboard_redirect(user: User = Depends(get_current_user)):
    role = user.role.value if hasattr(user.role, "value") else str(user.role)

    if role == UserRole.SUPERUSER.value:
        return RedirectResponse("/dashboards/l0", status_code=status.HTTP_302_FOUND)

    if role == UserRole.REGION_ADMIN.value:
        return RedirectResponse("/dashboards/l1", status_code=status.HTTP_302_FOUND)

    if role == UserRole.DISTRICT_ADMIN.value:
        return RedirectResponse("/dashboards/l2", status_code=status.HTTP_302_FOUND)

    if role == UserRole.SCHOOL_ADMIN.value:
        return RedirectResponse("/dashboards/l3", status_code=status.HTTP_302_FOUND)

    if role == UserRole.SCHOOL_STAFF.value:
        return RedirectResponse("/dashboards/staff_school", status_code=status.HTTP_302_FOUND)

    return RedirectResponse("/login", status_code=status.HTTP_302_FOUND)


@router.get("/dashboards/l0", response_class=HTMLResponse, name="dashboard_l0")
async def dashboard_l0(
    request: Request,
    user: User = Depends(require_roles(UserRole.SUPERUSER)),
):
    return templates.TemplateResponse(
        request,
        "dashboards/l0.html",
        {
            "request": request,
            "user": user,
        },
    )