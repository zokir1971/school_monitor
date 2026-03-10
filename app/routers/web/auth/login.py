# app/routers/web/auth/login.py

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession
from app.routers.web.web_common import templates

from app.db.session import get_db
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.modules.users.services.auth_service import UserAuthService
from app.routers.web.helpers.navigation import dashboard_url_for_role
from app.routers.web.helpers.render import render, render_error

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(exists().where(User.role == UserRole.SUPERUSER))
    )
    superuser_exists = bool(res.scalar())

    return render(
        templates,
        request,
        "auth/login.html",
        {
            "can_bootstrap_superuser": not superuser_exists,
            "error": None,
        },
    )


@router.post("/login")
async def login_submit(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await UserAuthService.authenticate(
        db,
        identifier=identifier,
        password=password,
    )

    if not user:
        return render_error(
            templates,
            request,
            "auth/login.html",
            ctx={},
            error="Неверный логин/ИИН или пароль",
            status_code=400,
        )

    response = RedirectResponse(
        url=dashboard_url_for_role(user.role),
        status_code=303,
    )

    response.set_cookie(
        "user_id",
        str(user.id),
        httponly=True,
        samesite="lax",
    )

    return response
