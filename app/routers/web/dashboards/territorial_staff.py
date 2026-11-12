"""Staff landing pages: shared bank entry, no administrator privileges."""
from fastapi import APIRouter, Depends, Request
from app.modules.users.deps import require_roles, resolve_workspace_context
from app.modules.users.enums import UserRole
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router = APIRouter()

@router.get('/dashboards/staff_region', name='dashboard_staff_region')
async def region_staff(request: Request, user=Depends(require_roles(UserRole.REGION_STAFF)),
                       _workspace=Depends(resolve_workspace_context)):
    return render(templates, request, 'dashboards/territorial_staff.html',
                  {'user':user, 'panel_title':'Панель сотрудника региона'})

@router.get('/dashboards/staff_district', name='dashboard_staff_district')
async def district_staff(request: Request, user=Depends(require_roles(UserRole.DISTRICT_STAFF)),
                         _workspace=Depends(resolve_workspace_context)):
    return render(templates, request, 'dashboards/territorial_staff.html',
                  {'user':user, 'panel_title':'Панель сотрудника района'})
