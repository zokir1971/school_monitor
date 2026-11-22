from sqlalchemy.exc import IntegrityError
# app/routers/web/auth/register_admin_by_code.py

from app.core.i18n import resolve_language

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import raiseload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.org.models import Region, District, School
from app.modules.users.enums import UserRole
from app.modules.users.services.admin_registration import AdminRegistrationService
from app.modules.users.services.registration_code import RegistrationCodeService
from app.routers.web.web_common import templates
from app.routers.web.helpers.render import render, render_error

router = APIRouter()


async def _context_after_error(db, ctx):
    """Restore role/scope selectors after an error, without consuming the invite."""
    result = dict(ctx)
    try:
        code = await RegistrationCodeService.preview_code(db, invite_code=ctx["invite_code"])
    except ValueError:
        result["step"] = 1
        return result
    result["role"] = code.target_role
    if code.target_role == UserRole.REGION_ADMIN:
        query = select(Region).options(raiseload("*")).order_by(Region.name)
        if code.region_id:
            query = query.where(Region.id == code.region_id)
        result["regions"] = (await db.execute(query)).scalars().all()
    elif code.target_role == UserRole.DISTRICT_ADMIN and code.district_id:
        result["district"] = await db.get(District, code.district_id, options=[raiseload("*")])
    elif code.target_role == UserRole.SCHOOL_ADMIN and code.school_id:
        school = await db.get(School, code.school_id, options=[raiseload("*")])
        if school:
            result["school"] = school
            result["district"] = await db.get(District, school.district_id, options=[raiseload("*")]) if school.district_id else None
    return result


# Регистрация админа по коду
@router.get("/register-admin", response_class=HTMLResponse)
async def register_admin_page(request: Request):
    return render(
        templates,
        request,
        "auth/register_admin.html",
        {"step": 1},
    )


@router.post("/register-admin/preview", response_class=HTMLResponse)
async def register_admin_preview(
        request: Request,
        invite_code: str = Form(...),
        db: AsyncSession = Depends(get_db),
):
    invite_code_norm = invite_code.strip().upper()

    try:
        rc = await RegistrationCodeService.preview_code(db, invite_code=invite_code_norm)
    except ValueError:
        return render_error(
            templates,
            request,
            "auth/register_admin.html",
            {"step": 1, "invite_code": invite_code_norm},
            error="Недействительный/истёкший/отозванный код",
            status_code=400,
        )

    ctx = {"step": 2, "invite_code": invite_code_norm, "role": rc.target_role}

    if rc.target_role == UserRole.REGION_ADMIN:
        q = select(Region).options(raiseload("*")).order_by(Region.name)
        if rc.region_id:
            q = q.where(Region.id == rc.region_id)
        ctx["regions"] = (await db.execute(q)).scalars().all()
        return render(templates, request, "auth/register_admin.html", ctx)

    if rc.target_role == UserRole.DISTRICT_ADMIN:
        if not rc.district_id:
            return render_error(
                templates,
                request,
                "auth/register_admin.html",
                {"step": 1, "invite_code": invite_code_norm},
                error="Код повреждён: нет district_id",
                status_code=400,
            )
        ctx["district"] = await db.get(District, rc.district_id, options=[raiseload("*")])
        return render(templates, request, "auth/register_admin.html", ctx)

    if rc.target_role == UserRole.SCHOOL_ADMIN:
        if not rc.school_id:
            return render_error(
                templates,
                request,
                "auth/register_admin.html",
                {"step": 1, "invite_code": invite_code_norm},
                error="Код повреждён: нет school_id",
                status_code=400,
            )

        school = await db.get(School, rc.school_id, options=[raiseload("*")])
        if not school:
            return render_error(
                templates,
                request,
                "auth/register_admin.html",
                {"step": 1, "invite_code": invite_code_norm},
                error="Код указывает на несуществующую школу",
                status_code=400,
            )

        district = await db.get(District, school.district_id, options=[raiseload("*")]) if school.district_id else None
        ctx.update({"district": district, "school": school})
        return render(templates, request, "auth/register_admin.html", ctx)

    return render_error(
        templates,
        request,
        "auth/register_admin.html",
        {"step": 1, "invite_code": invite_code_norm},
        error="Эта роль не поддерживает регистрацию через код",
        status_code=400,
    )


@router.post("/register-admin")
async def register_admin_action(
        request: Request,
        invite_code: str = Form(...),
        username: str = Form(...),
        iin: str = Form(...),
        full_name: str = Form(...),
        password: str = Form(...),
        password2: str = Form(...),
        email: str = Form(...),
        phone: str = Form(...),
        region_id: int | None = Form(None),
        district_id: int | None = Form(None),
        school_id: int | None = Form(None),
        db: AsyncSession = Depends(get_db),
):
    invite_code_norm = invite_code.strip().upper()

    ctx = {
        "step": 2,
        "invite_code": invite_code_norm,
        "username": username,
        "iin": iin,
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "region_id": region_id,
        "district_id": district_id,
        "school_id": school_id,
    }

    if password != password2:
        return render_error(
            templates,
            request,
            "auth/register_admin.html",
            await _context_after_error(db, ctx),
            error="Пароли не совпадают",
            status_code=400,
        )

    try:
        await AdminRegistrationService.register_admin_with_code(
            db,
            code=invite_code_norm,
            username=username,
            full_name=full_name,
            iin=iin,
            password=password,
            selected_region_id=region_id,
            ui_language=resolve_language(request),
            email=email,
            phone=phone,
        )
    except (ValueError, IntegrityError) as e:
        await db.rollback()
        message = str(e) if isinstance(e, ValueError) else "Пользователь с такими данными уже зарегистрирован"
        return render_error(
            templates,
            request,
            "auth/register_admin.html",
            await _context_after_error(db, ctx),
            error=message,
            status_code=400,
        )

    return RedirectResponse("/login", status_code=303)
