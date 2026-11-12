# app/routers/web/dashboards/workspace_web.py

from __future__ import annotations

from typing import cast

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import RedirectResponse,HTMLResponse
from urllib.parse import urlsplit
from app.modules.users.workspace_choice import save_workspace
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

from app.modules.users.deps import (
    get_current_user,
    resolve_workspace_context,
)
from app.modules.users.enums import (
    UserRole,
    UserWorkspace,
)
from app.modules.users.models import User
from app.modules.users.schemas.workspace_schemas import (
    UserWorkspaceContextDTO,
)


router = APIRouter(
    prefix="/workspace",
    tags=["workspace"],
)


# ============================================================
# SWITCH WORKSPACE
# ============================================================


@router.post(
    "/switch",
    name="workspace_switch",
)
async def workspace_switch(
    request: Request,
    workspace: str = Form(...),
    user: User = Depends(get_current_user),
    workspace_context: UserWorkspaceContextDTO = Depends(
        resolve_workspace_context
    ),
):
    """
    Переключает рабочий интерфейс текущего пользователя.

    User.role не изменяется.

    Доступность workspace уже определена
    resolve_workspace_context и UserWorkspaceService.
    """

    # --------------------------------------------------------
    # 1. PARSE WORKSPACE
    # --------------------------------------------------------

    origin=request.headers.get('origin')
    if origin:
        actual=urlsplit(origin);expected=urlsplit(str(request.base_url))
        if (actual.scheme,actual.netloc)!=(expected.scheme,expected.netloc):
            raise HTTPException(403,'Cross-origin workspace switch is not allowed')
    try:
        requested_workspace = UserWorkspace(
            workspace
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Белгісіз жұмыс режимі.",
        ) from exc

    # --------------------------------------------------------
    # 2. ACCESS CHECK
    # --------------------------------------------------------

    available_workspaces = {
        item.code
        for item in workspace_context.items
    }

    if requested_workspace not in available_workspaces:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Бұл жұмыс режиміне "
                "қолжетімділік жоқ."
            ),
        )

    # --------------------------------------------------------
    # 3. SAVE ACTIVE WORKSPACE
    # --------------------------------------------------------

    # --------------------------------------------------------
    # 4. REDIRECT
    # --------------------------------------------------------

    redirect_url = _get_workspace_url(
        request=request,
        user=user,
        workspace=requested_workspace,
    )

    response=RedirectResponse(url=redirect_url,status_code=status.HTTP_303_SEE_OTHER)
    return save_workspace(request,response,user,requested_workspace)



# ============================================================
# WORKSPACE URL
# ============================================================


def _get_workspace_url(
    *,
    request: Request,
    user: User,
    workspace: UserWorkspace,
) -> str:
    """
    Возвращает стартовую страницу выбранного workspace.
    """

    if workspace == UserWorkspace.PRIMARY:
        return _get_primary_workspace_url(
            request=request,
            user=user,
        )

    if workspace == UserWorkspace.STAFF:
        return str(
            request.url_for(
                "dashboard_staff_school"
            )
        )

    if workspace == UserWorkspace.TEACHER:
        return str(
            request.url_for(
                "dashboard_teacher"
            )
        )

    if (
        workspace
        == UserWorkspace.QUESTION_BANK_EXPERT
    ):
        return str(
            request.url_for(
                "question_bank_expert_dashboard"
            )
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Жұмыс режимі анықталмады.",
    )


# ============================================================
# PRIMARY WORKSPACE URL
# ============================================================


def _get_primary_workspace_url(
    *,
    request: Request,
    user: User,
) -> str:
    """
    Возвращает основной dashboard пользователя
    согласно его глобальной UserRole.

    PRIMARY всегда означает исходный интерфейс
    глобальной роли пользователя.

    REGION_STAFF и DISTRICT_STAFF имеют отдельные панели
    с доступом к общему банку готовых заданий.
    """

    user_role = cast(
        UserRole,
        user.role,
    )

    # --------------------------------------------------------
    # SUPERUSER
    # --------------------------------------------------------

    if user_role in {
        UserRole.SUPERUSER,
    }:
        return str(
            request.url_for(
                "dashboard_l0"
            )
        )

    # --------------------------------------------------------
    # REGION ADMIN
    # --------------------------------------------------------

    if user_role in {
        UserRole.REGION_ADMIN,
    }:
        return str(
            request.url_for(
                "dashboard_l1"
            )
        )

    # --------------------------------------------------------
    # DISTRICT ADMIN
    # --------------------------------------------------------

    if user_role == UserRole.DISTRICT_ADMIN:
        return str(
            request.url_for(
                "dashboard_l2"
            )
        )

    # --------------------------------------------------------
    # SCHOOL ADMIN
    # --------------------------------------------------------

    if user_role == UserRole.SCHOOL_ADMIN:
        return str(
            request.url_for(
                "school_admin_dashboard"
            )
        )

    # --------------------------------------------------------
    # SCHOOL STAFF
    # --------------------------------------------------------

    if user_role == UserRole.SCHOOL_STAFF:
        return str(
            request.url_for(
                "dashboard_staff_school"
            )
        )

    # --------------------------------------------------------
    # TEACHER
    # --------------------------------------------------------

    if user_role == UserRole.TEACHER:
        return str(
            request.url_for(
                "dashboard_teacher"
            )
        )

    # --------------------------------------------------------
    # TERRITORIAL STAFF
    # --------------------------------------------------------

    if user_role == UserRole.REGION_STAFF:
        return str(request.url_for('dashboard_staff_region'))
    if user_role == UserRole.DISTRICT_STAFF:
        return str(request.url_for('dashboard_staff_district'))

    # --------------------------------------------------------
    # UNKNOWN ROLE
    # --------------------------------------------------------

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Негізгі жұмыс интерфейсі "
            "анықталмады."
        ),
    )


@router.get('',name='workspace_select',response_class=HTMLResponse)
async def workspace_select(request:Request,user:User=Depends(get_current_user),workspace_context:UserWorkspaceContextDTO=Depends(resolve_workspace_context)):
    response=render(templates,request,'dashboards/workspace_select.html',dict(user=user,workspace_context=workspace_context))
    response.headers['Cache-Control']='no-store'
    response.headers['Vary']='Cookie'
    return response
