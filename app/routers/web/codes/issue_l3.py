# app/routers/web/codes/issue_l3.py
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.org.models import District, School
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.service import RegistrationCodeService
from app.routers.web.helpers.issue_cache import cache_set, cache_get
from app.routers.web.web_common import templates
from app.utils.pdf_code import generate_codes_pdf

router = APIRouter()


# -----------------------
# DISTRICT_ADMIN: issue L3 code for SCHOOL_ADMIN
# -----------------------
@router.get("/l2/issue-l3", response_class=HTMLResponse)
async def l2_issue_l3_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.DISTRICT_ADMIN)),
):
    if not user.district_id:
        return templates.TemplateResponse(
            request,
            "dashboards/L2.html",
            {"user": user, "error": "У пользователя не задан district_id"},
            status_code=400,
        )
    # получаем список школ района из БД
    district = await db.get(District, user.district_id)
    schools = (await db.execute(
        select(School)
        .where(School.district_id == user.district_id)
        .order_by(School.name)
    )).scalars().all()

    return templates.TemplateResponse(
        request,
        "codes/issue_l3.html",
        {
            "user": user,
            "district": district,
            "schools": schools,
            "error": None,
            "can_bootstrap_superuser": False,
        },
    )


@router.post("/l2/issue-l3", response_class=HTMLResponse)
async def l2_issue_l3_submit(
        request: Request,
        school_ids: list[int] = Form(...),
        quota_total: int = Form(1),
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.DISTRICT_ADMIN)),
):
    schools_all = (await db.execute(
        select(School)
        .where(School.district_id == user.district_id)
        .order_by(School.name)
    )).scalars().all()

    school_map = {s.id: s.name for s in schools_all}
    allowed_ids = set(school_map.keys())

    if any(sid not in allowed_ids for sid in school_ids):
        return templates.TemplateResponse(
            request,
            "codes/issue_l3.html",
            {
                "user": user,
                "schools": schools_all,
                "error": "Нельзя выдавать коды для школ вне вашего района",
                "can_bootstrap_superuser": False,
            },
            status_code=400,
        )

    issued: list[dict] = []
    batch_id = str(uuid4())

    try:
        for sid in school_ids:
            raw_code, code_obj = await RegistrationCodeService.issue_l3_code(
                db,
                issued_by_user_id=user.id,
                school_id=sid,
                quota_total=quota_total,
                expires_days=30,
            )

            issued.append({
                "school_id": sid,
                "school_name": school_map.get(sid, "-"),
                "raw_code": raw_code,
                "quota_total": code_obj.quota_total,
                "expires_at": code_obj.expires_at.strftime("%d.%m.%Y") if code_obj.expires_at else "без срока",
            })
        await db.commit()

        cache_set(batch_id, {
            "issued": issued,
            "shown": False,
            "saved": False,
        })
    except ValueError as e:
        await db.rollback()
        return templates.TemplateResponse(
            request,
            "codes/issue_l3.html",
            {
                "request": request,
                "user": user,
                "issued": issued,
                "school": schools_all,
                "error": str(e),
            },
        )
    return RedirectResponse(url=f"/l2/issue-l3/result/{batch_id}", status_code=303)


# --- GET: показывает результат; при обновлении не редиректит, а показывает предупреждение ---
@router.get("/l2/issue-l3/result/{batch_id}", response_class=HTMLResponse)
async def l2_issue_l3_result(
        request: Request,
        batch_id: str,
        current_user=Depends(require_roles(UserRole.DISTRICT_ADMIN)),
):
    data = cache_get(batch_id)
    if not data:
        return templates.TemplateResponse(
            "codes/issue_result_expired.html",
            {"request": request, "user": current_user},
            status_code=410,
        )

    issued = data["issued"]
    saved = data["saved"]
    shown = data["shown"]

    show_codes = not shown
    if show_codes:
        data["shown"] = True
        cache_set(batch_id, data)

    return templates.TemplateResponse(
        "codes/issue_l3_result.html",
        {
            "request": request,
            "user": current_user,
            "batch_id": batch_id,
            "show_codes": show_codes,
            "saved": saved,
            "issued": issued,
            "count": len(issued),
        },
    )


# --- GET: сохранить PDF со ВСЕМИ кодами одной выдачи и пометить как сохранённые ---
@router.get("/l2/issue-l3/pdf/{batch_id}")
async def l2_issue_l3_pdf(
        batch_id: str,
        db: AsyncSession = Depends(get_db),
        _user=Depends(require_roles(UserRole.DISTRICT_ADMIN)),
):
    data = cache_get(batch_id)
    if not data:
        raise HTTPException(404, "Batch not found or expired")

    issued = data["issued"]

    district = await db.get(District, _user.district_id)
    if not district:
        raise HTTPException(404, "District not found")

    pdf_bytes = generate_codes_pdf(
        title="Коды регистрации администраторов школ (L3)",
        level_label="L3",
        issued=issued,
        scope_label="Район",
        scope_name=district.name,
        context_header="Школа",
    )

    data["saved"] = True
    cache_set(batch_id, data)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="issue_l3_{batch_id}.pdf"'
        },
    )
