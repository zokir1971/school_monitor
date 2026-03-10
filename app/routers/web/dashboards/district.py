# app/routers/web/dashboards/district.py


from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.routers.web.web_common import templates

router = APIRouter()


@router.get("/dashboards/l2", response_class=HTMLResponse)
async def dashboard_l2(
        request: Request,
        user=Depends(require_roles(UserRole.SUPERUSER, UserRole.DISTRICT_ADMIN)),
):
    return templates.TemplateResponse(
        request,
        "dashboards/l2.html",
        {"user": user},
    )
