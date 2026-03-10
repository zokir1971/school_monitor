from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.users.schemas import StaffRegisterDTO
from app.modules.users.services.staff_auth_service import (
    StaffAuthService,
    StaffRegistrationError, )
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router = APIRouter(prefix="/staff-auth", tags=["staff-auth"])


@router.get("/register", name="staff_register_page")
async def staff_register_page(request: Request):
    return render(
        templates,
        request,
        "auth/register_staff_schools.html",
        {
            "error": None,
            "form": {},
        },
    )


# принимаем данные из формы регистрации
'''
@router.post("/register", name="staff_register_submit")
async def staff_register_submit(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    print("FORM DATA:", dict(form))
    return {"form": dict(form)}

'''


@router.post("/register", name="staff_register_submit")
async def staff_register_submit(
        request: Request,
        iin: str = Form(...),
        username: str = Form(...),
        email: str = Form(""),
        phone: str = Form(""),
        password: str = Form(...),
        password2: str = Form(...),
        db: AsyncSession = Depends(get_db),
):
    dto = StaffRegisterDTO(
        iin=iin,
        username=username,
        email=email,
        phone=phone,
        password=password,
        password2=password2,
    )

    try:
        await StaffAuthService.register_staff_user(db, dto=dto)
    except StaffRegistrationError as e:
        return render(
            templates,
            request,
            "auth/register_staff_schools.html",
            {
                "error": str(e),
                "form": {
                    "iin": iin,
                    "username": username,
                    "email": email,
                    "phone": phone,
                },
            },
            status_code=400,
        )

    return RedirectResponse(
        url="/login?success=Регистрация прошла успешно. Теперь войдите в систему.",
        status_code=status.HTTP_303_SEE_OTHER,
    )
