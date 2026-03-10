# app/routers/web/dashboards/school.py


from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

from app.modules.planning.services import SchoolPlanningService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.routers.web.web_common import templates

router = APIRouter()


@router.get("/dashboards/l3", response_class=HTMLResponse)
async def dashboard_l3(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SUPERUSER, UserRole.SCHOOL_ADMIN)),
):
    academic_year = await SchoolPlanningService.get_active_academic_year(db)

    return templates.TemplateResponse(
        request,
        "dashboards/l3.html",
        {"user": user, "academic_year": academic_year},
    )
