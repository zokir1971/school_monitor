# app/routers/web/auth/login.py

from __future__ import annotations

import logging

from fastapi import (
    APIRouter,
    Depends,
    Form,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.core.i18n import resolve_language, set_language_cookie
from app.db.session import get_db
from app.modules.users.enums import (
    UserRole,
    UserWorkspace,
)
from app.modules.users.models import User
from app.modules.users.repo import UserRepo
from app.routers.web.helpers.navigation import (
    dashboard_url_for_role,
)
from app.routers.web.helpers.render import (
    render,
    render_error,
)
from app.routers.web.web_common import templates


router = APIRouter()

logger = logging.getLogger(__name__)


# ============================================================
# LOGIN PAGE
# ============================================================


@router.get(
    "/login",
    response_class=HTMLResponse,
)
async def login_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Страница входа.

    Дополнительно определяем, существует ли SUPERUSER,
    чтобы при необходимости показать первоначальную
    регистрацию главного администратора.
    """

    result = await db.execute(
        select(
            exists().where(
                User.role == UserRole.SUPERUSER
            )
        )
    )

    superuser_exists = bool(
        result.scalar()
    )

    return render(
        templates,
        request,
        "auth/login.html",
        {
            "can_bootstrap_superuser": (
                not superuser_exists
            ),
            "error": None,
        },
    )


# ============================================================
# LOGIN SUBMIT
# ============================================================


@router.post(
    "/login",
    name="login_submit",
)
async def login_submit(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Авторизация пользователя.

    После успешного входа пользователь всегда начинает
    работу со своего PRIMARY workspace.

    Дополнительные workspace:
        - STAFF
        - TEACHER
        - QUESTION_BANK_EXPERT

    выбираются пользователем через переключатель интерфейса.
    """

    # --------------------------------------------------------
    # 1. NORMALIZE IDENTIFIER
    # --------------------------------------------------------

    identifier = identifier.strip()

    # --------------------------------------------------------
    # 2. FIND USER
    # --------------------------------------------------------

    user = await UserRepo.get_by_identifier(
        db,
        identifier=identifier,
    )


    # --------------------------------------------------------
    # 3. PASSWORD CHECK
    # --------------------------------------------------------

    ok = (
        user is not None
        and bool(user.password_hash)
        and verify_password(
            password,
            str(user.password_hash),
        )
    )


    # --------------------------------------------------------
    # 4. INVALID LOGIN
    # --------------------------------------------------------

    if user is None or not ok:
        return render_error(
            templates,
            request,
            "auth/login.html",
            ctx={},
            error=(
                "Неверный логин/ИИН или пароль"
            ),
            status_code=400,
        )

    # --------------------------------------------------------
    # 5. ACTIVE USER CHECK
    # --------------------------------------------------------

    if not bool(user.is_active):
        return render_error(
            templates,
            request,
            "auth/login.html",
            ctx={},
            error=(
                "Учетная запись пользователя "
                "неактивна"
            ),
            status_code=403,
        )

    # --------------------------------------------------------
    # 6. RESET WORKSPACE
    # --------------------------------------------------------

    # Каждый новый login начинается с PRIMARY.
    #
    # Например:
    #
    # TEACHER
    #     PRIMARY -> Мұғалім
    #
    # SCHOOL_STAFF
    #     PRIMARY -> Қызметкер
    #
    # SCHOOL_ADMIN
    #     PRIMARY -> Мектеп әкімшісі
    #
    # SUPERUSER
    #     PRIMARY -> Бас әкімші
    #
    # Это также не позволяет workspace предыдущего входа
    # остаться активным после новой авторизации.

    from app.core.access_session import bind_session
    bind_session(request, user)

    request.session["active_workspace"] = (
        UserWorkspace.PRIMARY.value
    )

    # --------------------------------------------------------
    # 7. REDIRECT TO PRIMARY DASHBOARD
    # --------------------------------------------------------

    response = RedirectResponse(
        url=dashboard_url_for_role(
            user.role
        ),
        status_code=303,
    )

    # --------------------------------------------------------
    # 8. AUTH COOKIE
    # --------------------------------------------------------

    response.set_cookie(
        key="user_id",
        value=str(user.id),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )

    set_language_cookie(response, request, resolve_language(request, user))
    return response
