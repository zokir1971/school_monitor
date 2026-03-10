from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request
from fastapi import HTTPException
from fastapi import UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.modules.planning.enums import ResponsibleRole
from app.modules.staff.models_staff_school import SchoolStaffMember
from app.modules.staff.service_school_staff import SchoolStaffImportService, SchoolStaffRoleService
from app.modules.staff.staff_repo import SchoolStaffRepo
from app.modules.staff.utils.staff_position_filter import ALLOWED_POSITIONS
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.routers.web.web_common import templates

# если хочешь проверять должность по справочнику:
# from app.modules.staff.constants import ALLOWED_POSITIONS


router = APIRouter(
    prefix="/staff/school",
    tags=["School Staff (web)"],
)


def _require_school_id(user) -> int:
    school_id = getattr(user, "school_id", None)
    if not school_id:
        raise HTTPException(status_code=403, detail="Нет school_id")
    return int(school_id)


# =========================
# Staff page
# =========================
@router.get("", name="school_staff_page", response_class=HTMLResponse)
async def school_staff_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)

    q = (
        select(SchoolStaffMember)
        .where(SchoolStaffMember.school_id == school_id)
        .options(selectinload(SchoolStaffMember.roles))
        .order_by(
            SchoolStaffMember.is_active.desc(),
            SchoolStaffMember.full_name.asc(),
        )
    )

    members = (await db.execute(q)).scalars().all()
    allowed_positions = sorted(ALLOWED_POSITIONS["kz"])
    return templates.TemplateResponse(
        "staff/school_staff.html",
        {
            "user": user,
            "request": request,
            "members": members,
            "allowed_positions": allowed_positions
        },
    )


# =========================
# Create staff member
# =========================
@router.post("/members", name="school_staff_create_member", )
async def school_staff_create_member(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)

    form = await request.form()

    full_name = (form.get("full_name") or "").strip()
    iin = (form.get("iin") or "").strip()
    position_text = (form.get("position_text") or "").strip() or None

    if not full_name:
        return RedirectResponse(
            url="/staff/school?error=ФИО%20обязательно",
            status_code=303,
        )

    if not (iin.isdigit() and len(iin) == 12):
        return RedirectResponse(
            url="/staff/school?error=ИИН%20должен%20быть%2012%20цифр",
            status_code=303,
        )

    exists_q = select(SchoolStaffMember.id).where(
        SchoolStaffMember.school_id == school_id,
        SchoolStaffMember.iin == iin,
    )
    if (await db.execute(exists_q)).scalar_one_or_none():
        return RedirectResponse(
            url="/staff/school?error=ИИН%20уже%20существует",
            status_code=303,
        )

    db.add(
        SchoolStaffMember(
            school_id=school_id,
            full_name=full_name,
            iin=iin,
            position_text=position_text,
            is_active=True,
        )
    )

    await db.commit()

    return RedirectResponse(
        url="/staff/school?success=Сотрудник%20добавлен",
        status_code=303,
    )


@router.post("/import", name="school_staff_import")
async def school_staff_import(
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
        file: UploadFile = File(...),
):
    school_id = _require_school_id(user)

    if not file.filename.lower().endswith(".csv"):
        return RedirectResponse("/staff/school?error=Нужен%20CSV%20файл", status_code=303)

    raw = await file.read()

    report = await SchoolStaffImportService.import_csv(db, school_id=school_id, raw=raw)
    await db.commit()

    msg = f"Импорт:%20создано%20{report.created},%20обновлено%20{report.updated},%20пропущено%20{report.skipped},%20ошибок%20{report.errors}"
    return RedirectResponse(f"/staff/school?success={msg}", status_code=303)


@router.get("/members/{member_id}/edit", name="school_staff_member_edit", response_class=HTMLResponse)
async def school_staff_member_edit(
        request: Request,
        member_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)

    m = await SchoolStaffRepo.get_member(db, school_id=school_id, member_id=member_id)
    if not m:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    # Только казахские должности (если у тебя ALLOWED_POSITIONS = {"ru": set, "kz": set})
    allowed_positions = sorted(ALLOWED_POSITIONS["kz"])

    return templates.TemplateResponse(
        "staff/member_edit.html",
        {"user": user, "request": request, "m": m, "allowed_positions": allowed_positions},
    )


def _to_none(s: str | None) -> str | None:
    s = (s or "").strip()
    return s or None


def _to_int(s: str | None) -> int | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Некорректное число: {s}")


def _to_decimal_2(s: str | None) -> Decimal | None:
    s = (s or "").strip()
    if not s:
        return None
    # поддержим запятую
    s = s.replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise HTTPException(status_code=400, detail=f"Некорректное число (rating): {s}")
    # можно ограничить 2 знака:
    return d.quantize(Decimal("0.01"))


def _to_date(s: str | None) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)  # ожидает YYYY-MM-DD
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Некорректная дата: {s}")


def _to_bool_from_select(s: str | None) -> bool:
    # если в форме select "1"/"0"
    return (s or "").strip() == "1"


@router.post("/members/{member_id}/edit", name="school_staff_member_edit_save")
async def school_staff_member_edit_save(
        request: Request,
        member_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)
    form = await request.form()

    # 1) получаем сотрудника (проверка школы)
    m = await SchoolStaffRepo.get_member(db, school_id=school_id, member_id=member_id)
    if not m:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    # 2) читаем все редактируемые поля (кроме iin/full_name)
    position_text = _to_none(form.get("position_text"))
    if not position_text:
        raise HTTPException(status_code=400, detail="Должность обязательна")

    # если хочешь строгую проверку должности (только KZ):
    # if position_text not in ALLOWED_POSITIONS["kz"]:
    #     raise HTTPException(status_code=400, detail="Недопустимая должность")

    m.education = _to_none(form.get("education"))
    m.academic_degree = _to_none(form.get("academic_degree"))
    m.position_text = position_text
    m.university = _to_none(form.get("university"))
    m.graduation_date = _to_date(form.get("graduation_date"))
    m.diploma_no = _to_none(form.get("diploma_no"))
    m.diploma_specialty = _to_none(form.get("diploma_specialty"))
    m.study_type = _to_none(form.get("study_type"))
    m.affiliation = _to_none(form.get("affiliation"))

    m.ped_start_date = _to_date(form.get("ped_start_date"))
    m.total_experience_years = _to_int(form.get("total_experience_years"))
    m.ped_experience_years = _to_int(form.get("ped_experience_years"))

    m.qualification_category = _to_none(form.get("qualification_category"))
    m.qualification_order_no = _to_none(form.get("qualification_order_no"))
    m.qualification_order_date = _to_date(form.get("qualification_order_date"))
    m.attestation_date = _to_date(form.get("attestation_date"))
    m.reattestation_date = _to_date(form.get("reattestation_date"))

    m.course_passed_date = _to_date(form.get("course_passed_date"))
    m.course_due_date = _to_date(form.get("course_due_date"))
    m.course_place = _to_none(form.get("course_place"))
    m.course_certificate_no = _to_none(form.get("course_certificate_no"))

    m.subject = _to_none(form.get("subject"))
    m.awards = _to_none(form.get("awards"))
    m.creative_topic = _to_none(form.get("creative_topic"))

    m.rating = _to_decimal_2(form.get("rating"))

    await db.commit()

    return RedirectResponse(url="/staff/school?success=Сохранено", status_code=303)


@router.post("/members/{member_id}/restore", name="school_staff_restore_member")
async def school_staff_restore_member(
        member_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)

    m = await SchoolStaffRepo.get_member(db, school_id=school_id, member_id=member_id)
    if not m:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    # если уже активен — можно просто вернуть
    if m.is_active:
        return RedirectResponse(
            url="/staff/school?info=Сотрудник%20уже%20активен",
            status_code=303,
        )

    m.is_active = True

    await db.commit()

    return RedirectResponse(
        url="/staff/school?success=Сотрудник%20восстановлен",
        status_code=303,
    )


ROLE_KEY_RE = re.compile(r"^roles\[(\d+)]\.(role|context)$")


@router.get("/members/{member_id}/roles", name="school_staff_member_roles_page", response_class=HTMLResponse)
async def roles_page(
        request: Request,
        member_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)

    m = await SchoolStaffRepo.get_member(db, school_id=school_id, member_id=member_id)
    member_roles = await SchoolStaffRoleService.get_member_roles_for_edit(db, school_id=school_id, member_id=member_id)

    responsible_roles = [{"value": r.value, "label_kz": r.label_kz} for r in ResponsibleRole.__members__.values()]

    return templates.TemplateResponse(
        "staff/member_roles.html",
        {"user": user, "request": request, "m": m, "responsible_roles": responsible_roles, "member_roles": member_roles},
    )


@router.post("/members/{member_id}/roles", name="school_staff_member_roles_save")
async def roles_save(
        request: Request,
        member_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)
    form = await request.form()

    tmp: dict[int, dict[str, str]] = {}
    for k, v in form.items():
        m = ROLE_KEY_RE.match(k)
        if not m:
            continue
        idx = int(m.group(1))
        field = m.group(2)
        tmp.setdefault(idx, {})[field] = (v or "").strip()

    roles: list[dict[str, str]] = []
    for idx in sorted(tmp.keys()):
        role_val = (tmp[idx].get("role") or "").strip()
        ctx = (tmp[idx].get("context") or "").strip()
        if role_val:
            roles.append({"role": role_val, "context": ctx})

    await SchoolStaffRoleService.replace_member_roles(
        db, school_id=school_id, member_id=member_id, roles=roles
    )
    await db.commit()

    return RedirectResponse(
        url=str(request.url_for("school_staff_page")) + "?success=Сохранено",
        status_code=303,
    )
