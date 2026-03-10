# app/routers/web/setup/superuser.py

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import get_db
from app.modules.users.services.bootstrap import BootstrapService
from app.modules.users.validators import validate_iin, validate_email, validate_kz_phone
from app.routers.web.web_common import templates

router = APIRouter()


# обработка страницы superuser
@router.get("/setup/superuser")
async def setup_superuser_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
):
    allowed = await BootstrapService.can_bootstrap_superuser(db)
    if not allowed:
        return templates.TemplateResponse(
            "auth/setup/superuser_done.html",
            {"request": request, "can_bootstrap_superuser": False},
            status_code=403,
        )

    return templates.TemplateResponse(
        "auth/setup/superuser_register.html",
        {"request": request, "error": None, "can_bootstrap_superuser": True},
    )


# регистрация, супер администратор (L0)
@router.post("/setup/superuser")
async def setup_superuser_submit(
        request: Request,
        username: str = Form(...),
        iin: str = Form(...),
        full_name: str = Form(...),
        email: str = Form(...),
        phone: str = Form(...),
        password: str = Form(...),
        password2: str = Form(...),
        db: AsyncSession = Depends(get_db),
):
    # 1) если L0 уже есть — закрываем
    allowed = await BootstrapService.can_bootstrap_superuser(db)
    if not allowed:
        return templates.TemplateResponse(
            "auth/setup/superuser_done.html",
            {"request": request, "can_bootstrap_superuser": False},
            status_code=403,
        )

    # 2) валидация паролей
    if password != password2:
        return templates.TemplateResponse(
            "auth/setup/superuser_register.html",
            {
                "request": request,
                "error": "Пароли не совпадают",
                "can_bootstrap_superuser": True,
            },
            status_code=400,
        )

    # 3) нормализация/валидация полей
    try:
        username = username.strip()
        full_name = full_name.strip()
        iin = validate_iin(iin)
        email = validate_email(email)
        phone = validate_kz_phone(phone)
        password_hash = hash_password(password)

        await BootstrapService.create_superuser(
            db,
            username=username,
            full_name=full_name,
            iin=iin,
            email=email,
            phone=phone,
            password_hash=password_hash,
        )

    except ValueError as e:
        return templates.TemplateResponse(
            "auth/setup/superuser_register.html",
            {
                "request": request,
                "error": str(e),
                "can_bootstrap_superuser": True,
            },
            status_code=400,
        )

    # 4) успех → на логин
    return RedirectResponse(url="/login", status_code=303)
