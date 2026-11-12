# app/routers/web/dashboards/district.py


from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.modules.users.deps import require_roles, resolve_workspace_context
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.modules.users.schemas import UserWorkspaceContextDTO
from app.routers.web.dashboards.workspace_render import render_dashboard as render
from app.modules.users.enums import UserWorkspace
from app.routers.web.web_common import templates

router = APIRouter()


@router.get(
    "/dashboards/l2",
    name="dashboard_l2",
    response_class=HTMLResponse,
)
async def dashboard_l2(
    request: Request,
    user: User = Depends(
        require_roles(
            UserRole.SUPERUSER,
            UserRole.DISTRICT_ADMIN,
        )
    ),
    _workspace_context: UserWorkspaceContextDTO = Depends(
        resolve_workspace_context
    ),
):
    return render(
        templates,
        request,
        "dashboards/l2.html",
        {
            "user": user,
        },
        workspace=UserWorkspace.PRIMARY,
    )
