# app/routers/web/codes/issue_l1.py

from uuid import uuid4

from fastapi import APIRouter, Form, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.org.models import Region
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.service import RegistrationCodeService
from app.routers.web.helpers.issue_cache import cache_set, cache_get
from app.routers.web.web_common import templates
from app.utils.pdf_code import generate_codes_pdf

router = APIRouter()


# -----------------------
# SUPERUSER: issue L1 code for Region
# -----------------------
@router.get("/super/issue-l1", response_class=HTMLResponse)
async def super_issue_l1_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_roles(UserRole.SUPERUSER)),
):
    # 1) получаем список областей из БД (их обычно немного)
    regions = (await db.execute(select(Region).order_by(Region.name))).scalars().all()

    # 2) отдаём страницу с готовым списком regions для <select>
    return templates.TemplateResponse(
        "codes/issue_l1.html",
        {
            "request": request,
            "user": current_user,
            "regions": regions,
            "error": None,
            "can_bootstrap_superuser": False,
        },
    )


# --- POST: создаёт коды и редиректит на страницу результата (PRG) ---
@router.post("/super/issue-l1")
async def super_issue_l1_submit(
        request: Request,
        region_ids: list[int] = Form(default_factory=list),
        quota_total: int = Form(1),
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_roles(UserRole.SUPERUSER)),
):
    # Список регионов для повторного показа формы (и мапа id->name)
    regions = (await db.execute(select(Region).order_by(Region.name))).scalars().all()
    region_map = {r.id: r.name for r in regions}

    if not region_ids:
        return templates.TemplateResponse(
            "codes/issue_l1.html",
            {
                "request": request,
                "user": current_user,
                "regions": regions,
                "error": "Выберите хотя бы один регион",
            },
            status_code=400,
        )

    issued: list[dict] = []
    batch_id = str(uuid4())

    try:
        for rid in region_ids:
            raw_code, code_obj = await RegistrationCodeService.issue_l1_code(
                db,
                issued_by_user_id=current_user.id,
                region_id=rid,
                quota_total=quota_total,
                expires_days=30,
            )

            issued.append({
                "region_id": rid,
                "region_name": region_map.get(rid, "-"),
                "raw_code": raw_code,  # строка
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
            "codes/issue_l1.html",
            {
                "request": request,
                "user": current_user,
                "regions": regions,
                "error": str(e),
            },
            status_code=400,
        )

    return RedirectResponse(url=f"/super/issue-l1/result/{batch_id}", status_code=303)


# --- GET: показывает результат; при обновлении не редиректит, а показывает предупреждение ---
@router.get("/super/issue-l1/result/{batch_id}", response_class=HTMLResponse)
async def super_issue_l1_result(
        request: Request,
        batch_id: str,
        current_user=Depends(require_roles(UserRole.SUPERUSER)),
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
        "codes/issue_l1_result.html",
        {
            "request": request,
            "user": current_user,
            "batch_id": batch_id,
            "show_codes": show_codes,
            "saved": saved,
            "issued": issued,  # всегда полный список
            "count": len(issued),
        },
    )


# --- GET: сохранить PDF со ВСЕМИ кодами одной выдачи и пометить как сохранённые ---
@router.get("/super/issue-l1/pdf/{batch_id}")
async def super_issue_l1_pdf(
        batch_id: str,
        _user=Depends(require_roles(UserRole.SUPERUSER)),
):
    data = cache_get(batch_id)
    if not data:
        raise HTTPException(404, "Batch not found or expired")

    issued = data["issued"]

    pdf_bytes = generate_codes_pdf(
        title="Коды регистрации администраторов регионов (L1)",
        level_label="L1",
        issued=issued,
        context_header="Регион",
    )

    data["saved"] = True
    cache_set(batch_id, data)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="issue_l1_{batch_id}.pdf"'
        },
    )
