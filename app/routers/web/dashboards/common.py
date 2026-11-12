# app/routers/web/dashboards/common.py

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette import status

from app.modules.users.deps import get_current_user, require_roles, resolve_workspace_context
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.web_common import templates
from app.modules.users.enums import UserWorkspace
from app.routers.web.dashboards.workspace_web import _get_workspace_url
from app.routers.web.dashboards.workspace_render import render_dashboard

router = APIRouter()


@router.get("/dashboards", name="dashboard_redirect")
async def dashboard_redirect(request: Request,user: User = Depends(get_current_user),workspace_context=Depends(resolve_workspace_context)):
    if workspace_context.active!=UserWorkspace.PRIMARY:
        return RedirectResponse(_get_workspace_url(request=request,user=user,workspace=workspace_context.active),status_code=303,headers={'Cache-Control':'no-store','Vary':'Cookie'})
    role = user.role.value if hasattr(user.role, "value") else str(user.role)

    if role == UserRole.SUPERUSER.value:
        return RedirectResponse("/dashboards/l0", status_code=status.HTTP_302_FOUND,headers={"Cache-Control":"no-store","Vary":"Cookie"})

    if role == UserRole.REGION_ADMIN.value:
        return RedirectResponse("/dashboards/l1", status_code=status.HTTP_302_FOUND,headers={"Cache-Control":"no-store","Vary":"Cookie"})

    if role == UserRole.DISTRICT_ADMIN.value:
        return RedirectResponse("/dashboards/l2", status_code=status.HTTP_302_FOUND,headers={"Cache-Control":"no-store","Vary":"Cookie"})

    if role == UserRole.SCHOOL_ADMIN.value:
        return RedirectResponse("/dashboards/l3", status_code=status.HTTP_302_FOUND,headers={"Cache-Control":"no-store","Vary":"Cookie"})

    if role == UserRole.SCHOOL_STAFF.value:
        return RedirectResponse("/dashboards/staff_school", status_code=status.HTTP_302_FOUND,headers={"Cache-Control":"no-store","Vary":"Cookie"})
    
    if role == UserRole.TEACHER.value:
        return RedirectResponse("/dashboards/teacher", status_code=status.HTTP_302_FOUND,headers={"Cache-Control":"no-store","Vary":"Cookie"})

    if role == UserRole.REGION_STAFF.value:
        return RedirectResponse('/dashboards/staff_region', status_code=status.HTTP_302_FOUND,headers={"Cache-Control":"no-store","Vary":"Cookie"})
    if role == UserRole.DISTRICT_STAFF.value:
        return RedirectResponse('/dashboards/staff_district', status_code=status.HTTP_302_FOUND,headers={"Cache-Control":"no-store","Vary":"Cookie"})

    return RedirectResponse("/login", status_code=status.HTTP_302_FOUND,headers={"Cache-Control":"no-store","Vary":"Cookie"})


@router.get("/dashboards/l0", response_class=HTMLResponse, name="dashboard_l0")
async def dashboard_l0(
    request: Request,
    user: User = Depends(require_roles(UserRole.SUPERUSER)),
    _workspace_context=Depends(resolve_workspace_context),
):
    return render_dashboard(templates,
        request,
        "dashboards/l0.html",
        {
            "request": request,
            "user": user,
        },
    )
