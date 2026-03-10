# app/routers/web/dashboards/region.py

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.routers.web.web_common import templates

router = APIRouter()


@router.get("/dashboards/l1", response_class=HTMLResponse)
async def dashboard_l1(
        request: Request,
        user=Depends(require_roles(UserRole.SUPERUSER, UserRole.REGION_ADMIN)),
):
    return templates.TemplateResponse(
        request,
        "dashboards/l1.html",
        {"user": user},
    )
