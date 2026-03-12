# app/routers/web/auth/login.py

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.db.session import get_db
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.modules.users.repo import UserRepo
from app.routers.web.helpers.navigation import dashboard_url_for_role
from app.routers.web.helpers.render import render, render_error
from app.routers.web.web_common import templates

router = APIRouter()

logger = logging.getLogger(__name__)


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
    identifier = identifier.strip()

    user = await UserRepo.get_by_identifier(db, identifier=identifier)

    logger.info("LOGIN DEBUG identifier=%r user_found=%s", identifier, bool(user))

    if user:
        logger.info(
            "LOGIN DEBUG password_len=%s password_bytes=%s hash_prefix=%r",
            len(password),
            len(password.encode("utf-8")),
            user.password_hash[:20] if user.password_hash else None,
        )

    ok = user is not None and verify_password(password, str(user.password_hash))

    logger.info("LOGIN DEBUG verify_result=%s", ok)

    if not user or not ok:
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
