# app/routers/web/codes/issue_l2.py
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.org.models import Region, District
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.service import RegistrationCodeService
from app.routers.web.helpers.issue_cache import cache_get, cache_set
from app.routers.web.web_common import templates
from app.utils.pdf_code import generate_codes_pdf

router = APIRouter()


# -----------------------
# REGION USER: issue L2 code for DISTRICT_ADMIN
# -----------------------
@router.get("/l1/issue-l2", response_class=HTMLResponse)
async def l1_issue_l2_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.REGION_ADMIN)),
):
    if not user.region_id:
        return templates.TemplateResponse(
            request,
            "dashboards/L1.html",
            {"user": user, "error": "У пользователя не задан region_id"},
            status_code=400,
        )
    # получаем список районов региона из БД (их обычно немного)
    region = await db.get(Region, user.region_id)
    districts = (await db.execute(
        select(District)
        .where(District.region_id == user.region_id)
        .order_by(District.name)
    )).scalars().all()

    return templates.TemplateResponse(
        request,
        "codes/issue_l2.html",
        {
            "user": user,
            "region": region,
            "districts": districts,
            "error": None,
            "can_bootstrap_superuser": False,
        },
    )


@router.post("/l1/issue-l2", response_class=HTMLResponse)
async def l1_issue_l2_submit(
        request: Request,
        district_ids: list[int] = Form(...),
        quota_total: int = Form(1),
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.REGION_ADMIN)),
):
    districts_all = (await db.execute(
        select(District)
        .where(District.region_id == user.region_id)
        .order_by(District.name)
    )).scalars().all()
    district_map = {d.id: d.name for d in districts_all}

    # защита от подмены district_id
    allowed_ids = set(district_map.keys())
    if any(did not in allowed_ids for did in district_ids):
        return templates.TemplateResponse(
            request,
            "codes/issue_l2.html",
            {
                "user": user,
                "districts": districts_all,
                "error": "Нельзя выдавать коды для чужих районов",
                "can_bootstrap_superuser": False,
            },
            status_code=400,
        )

    issued: list[dict] = []
    batch_id = str(uuid4())

    try:
        for did in district_ids:
            raw_code, code_obj = await RegistrationCodeService.issue_l2_code(
                db,
                issued_by_user_id=user.id,
                region_id=user.region_id,
                district_id=did,
                quota_total=quota_total,
                expires_days=30,
            )
            issued.append({
                "district_id": did,
                "district_name": district_map.get(did, "-"),
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
            "codes/issue_l2.html",
            {
                "request": request,
                "user": user,
                "issued": issued,
                "districts": districts_all,
                "error": str(e),
            },
            status_code=400,
        )

    return RedirectResponse(url=f"/l1/issue-l2/result/{batch_id}", status_code=303)


# --- GET: показывает результат; при обновлении не редиректит, а показывает предупреждение ---
@router.get("/l1/issue-l2/result/{batch_id}", response_class=HTMLResponse)
async def l1_issue_l2_result(
        request: Request,
        batch_id: str,
        current_user=Depends(require_roles(UserRole.REGION_ADMIN)),
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
        "codes/issue_l2_result.html",
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
@router.get("/l1/issue-l2/pdf/{batch_id}")
async def l1_issue_l2_pdf(
        batch_id: str,
        db: AsyncSession = Depends(get_db),
        _user=Depends(require_roles(UserRole.REGION_ADMIN)),
):
    data = cache_get(batch_id)
    if not data:
        raise HTTPException(404, "Batch not found or expired")

    issued = data["issued"]
    region = await db.get(Region, _user.region_id)

    pdf_bytes = generate_codes_pdf(
        title="Коды регистрации администраторов районов (L2)",
        level_label="L2",
        issued=issued,
        scope_label="Область",
        scope_name=region.name,
        context_header="Район",
    )

    data["saved"] = True
    cache_set(batch_id, data)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="issue_l2_{batch_id}.pdf"'
        },
    )
