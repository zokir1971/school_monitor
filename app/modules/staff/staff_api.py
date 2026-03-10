# app/modules/staff/staff_api.py

from fastapi import APIRouter, Depends, Request, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

import re

from app.db.session import get_db
from app.modules.planning.enums import ResponsibleRole
from app.modules.staff.utils.staff_position_filter import ALLOWED_POSITIONS
from app.modules.users.deps import require_roles
from app.routers.web.web_common import templates
from app.modules.users.enums import UserRole
from app.modules.staff.service_school_staff import SchoolStaffService

router = APIRouter(prefix="/staff/school", tags=["School Staff"])


def _require_school_id(user) -> int:
    if not getattr(user, "school_id", None):
        raise HTTPException(403, "Нет school_id")
    return user.school_id


@router.get("", name="school_staff_page")
async def school_staff_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)
    data = await SchoolStaffService.page_data(db, school_id=school_id)
    return templates.TemplateResponse(
        "staff/school_staff.html",
        {"request": request, **data},
    )


ROLE_KEY_RE = re.compile(r"^roles\[(\d+)]\.(role|context)$")


@router.post("/members", name="school_staff_create_member")
async def school_staff_create_member(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)

    form = await request.form()
    full_name = (form.get("full_name") or "").strip()
    iin = (form.get("iin") or "").strip()
    position_text = (form.get("position_text") or "").strip()  # ✅ из select

    # ✅ валидация
    if not full_name:
        raise HTTPException(status_code=400, detail="ФИО обязательно")
    if not (iin.isdigit() and len(iin) == 12):
        raise HTTPException(status_code=400, detail="ИИН должен быть 12 цифр")
    if not position_text:
        raise HTTPException(status_code=400, detail="Должность обязательна")

    # ✅ строгая проверка должности (без ручного ввода)
    if position_text.lower() not in ALLOWED_POSITIONS:
        raise HTTPException(status_code=400, detail="Недопустимая должность")

    # ✅ парсим роли, выбранные пользователем (roles[0].role / roles[0].context)
    tmp: dict[int, dict[str, str]] = {}
    for k, v in form.items():
        m = ROLE_KEY_RE.match(k)
        if not m:
            continue
        idx = int(m.group(1))
        field = m.group(2)  # "role" | "context"
        tmp.setdefault(idx, {})[field] = (v or "").strip()

    roles: list[dict[str, str]] = []
    for idx in sorted(tmp.keys()):
        role_val = (tmp[idx].get("role") or "").strip()
        ctx = (tmp[idx].get("context") or "").strip()
        if role_val:
            roles.append({"role": role_val, "context": ctx})

    # ✅ валидация ролей по enum (если роли необязательны — пустой список ок)
    allowed_roles = {r.value for r in ResponsibleRole.__members__.values()}
    for r in roles:
        if r["role"] not in allowed_roles:
            raise HTTPException(status_code=400, detail=f"Недопустимая роль: {r['role']}")

    await SchoolStaffService.create_member(
        db,
        school_id=school_id,
        full_name=full_name,
        iin=iin,
        position_text=position_text,
        roles=roles,
    )
    await db.commit()

    return RedirectResponse(url="/staff/school", status_code=303)


@router.post("/members/{member_id}/dismiss", name="school_staff_dismiss_member")
async def school_staff_dismiss_member(
        member_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)
    await SchoolStaffService.dismiss_member(db, school_id=school_id, member_id=member_id)
    await db.commit()
    return RedirectResponse(url="/staff/school", status_code=303)
