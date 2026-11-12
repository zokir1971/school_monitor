# app/routers/web/dashboards/school.py


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
    "/dashboards/l3",
    name="school_admin_dashboard",
    response_class=HTMLResponse,
)
async def school_admin_dashboard(
    request: Request,
    user: User = Depends(
        require_roles(
            UserRole.SCHOOL_ADMIN,
        )
    ),
    _workspace_context: UserWorkspaceContextDTO = Depends(
        resolve_workspace_context
    ),
):
    return render(
        templates,
        request,
        "dashboards/l3.html",
        {
            "user": user,
        },
        workspace=UserWorkspace.PRIMARY,
    )
