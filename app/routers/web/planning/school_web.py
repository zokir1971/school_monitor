# app/routers/web/planning/school_web.py
from __future__ import annotations

import traceback
from typing import cast

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import HTMLResponse, RedirectResponse, JSONResponse

from app.db.session import get_db
from app.db.types import enum_items
from app.modules.org.models import School
from app.modules.planning.enums import PlanStatus, ResponsibleRole, ReviewPlace
from app.modules.reports.enums import DocumentType
from app.modules.planning.models_school import SchoolPlan, SchoolPlanRow11, SchoolPlanRow4
from app.modules.planning.repo_school import SchoolPlanningRepo
from app.modules.planning.services.plan_export_service import SchoolPlanExportService
from app.modules.planning.services.school_service import (
    SchoolPlanEditService,
    SchoolPlanningService,
    SchoolRowsService,
)
from app.modules.planning.validators import normalize_months_text_to_list
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates
from app.utils.plan_vshk_pdf import ApprovalMeta, PlanVshkPdf

router = APIRouter(prefix="/planning/school", tags=["Planning.School.Web"])


# =========================================================
# helpers (убираем дублирование)
# =========================================================
def _normalize_academic_year(v: str | None) -> str:
    v = (v or "").strip()
    return v or "2025-2026"


def _normalize_tab(v: str | None) -> str:
    v = (v or "my").strip()
    return v if v in ("my", "active", "archive") else "my"


def _require_school_id(user) -> int:
    school_id = getattr(user, "school_id", None)
    if not school_id:
        raise HTTPException(status_code=400, detail="У пользователя не задана school_id")
    return int(school_id)


async def _get_school_or_400(db: AsyncSession, *, school_id: int) -> School:
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=400, detail="Школа пользователя не найдена")
    return cast(School, school)


async def _get_plan_or_404(
        db: AsyncSession,
        *,
        plan_id: int,
        school_id: int,
) -> SchoolPlan:
    plan: SchoolPlan | None = await SchoolPlanningRepo.get_school_plan(
        db,
        plan_id=plan_id,
        school_id=school_id,
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="План не найден")
    return plan


def _pick_active_plan(plans) -> object | None:
    # логика как была: сначала ACTIVE, если нет — DRAFT
    for p in plans:
        if p.status == PlanStatus.ACTIVE:
            return p
    for p in plans:
        if p.status == PlanStatus.DRAFT:
            return p
    return None


def row_months_selected(row) -> set[int]:
    pv = getattr(row, "period_values", None)
    if not pv:
        return set()
    return set(normalize_months_text_to_list(pv))


MONTH_NAMES = {
    1: "Қаңтар", 2: "Ақпан", 3: "Наурыз", 4: "Сәуір",
    5: "Мамыр", 6: "Маусым", 7: "Шілде", 8: "Тамыз",
    9: "Қыркүйек", 10: "Қазан", 11: "Қараша", 12: "Желтоқсан",
}


# -----------------------------
# 1) Dashboard (HTML)
# -----------------------------
@router.get("/", name="school_dashboard")
async def school_dashboard(
        request: Request,
        academic_year: str | None = None,
        tab: str | None = None,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    year = _normalize_academic_year(academic_year)
    tab_val = _normalize_tab(tab)

    school_id = _require_school_id(user)
    school = await _get_school_or_400(db, school_id=school_id)

    templates_active = await SchoolPlanningRepo.list_active_templates(db)
    plans = await SchoolPlanningRepo.list_school_plans(db, school_id=school_id, academic_year=year)

    active_template_id = templates_active[0].id if templates_active else None
    active_plan = _pick_active_plan(plans)

    return render(
        templates,
        request,
        "planning/school/school_dashboard.html",
        {
            "user": user,
            "school": school,
            "academic_year": year,
            "tab": tab_val,
            "templates_active": templates_active,
            "active_template_id": active_template_id,
            "plans": plans,
            "active_plan": active_plan,
            "PlanStatus": PlanStatus,
        },
    )


# -----------------------------
# 2) Create plan from template
# -----------------------------
@router.post("/create")
async def school_create_plan(
        request: Request,
        template_id: int = Form(...),
        academic_year: str = Form(...),
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    year = _normalize_academic_year(academic_year)
    school_id = _require_school_id(user)

    # для корректного возврата страницы с ошибкой
    school = await _get_school_or_400(db, school_id=school_id)

    templates_active = await SchoolPlanningRepo.list_active_templates(db)
    plans = await SchoolPlanningRepo.list_school_plans(db, school_id=school_id, academic_year=year)
    active_template_id = template_id if template_id else (templates_active[0].id if templates_active else None)

    try:
        result = await SchoolPlanningService.create_plan_from_template(
            db,
            school_id=school_id,
            template_id=template_id,
            academic_year=year,
            allow_multiple_per_year=False,
        )
    except ValueError as e:
        return render(
            templates,
            request,
            "planning/school/school_dashboard.html",
            {
                "user": user,
                "school": school,
                "academic_year": year,
                "tab": "my",
                "templates_active": templates_active,
                "active_template_id": active_template_id,
                "plans": plans,
                "active_plan": _pick_active_plan(plans),
                "error": str(e),
                "PlanStatus": PlanStatus,
            },
            status_code=400,
        )

    return RedirectResponse(url=f"/planning/school/plan/{result.plan_id}", status_code=303)


# -----------------------------
# 3) View plan (choose direction)
# -----------------------------
@router.get("/plan/{plan_id}", name="school_plan_view")
async def school_plan_view(
        request: Request,
        plan_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)

    plan = await _get_plan_or_404(db, plan_id=plan_id, school_id=school_id)

    # направления из шаблона
    tds = await SchoolPlanningRepo.list_plan_directions(
        db, template_id=plan.template_id
    )

    # строки годового плана
    rows11 = (
        await db.execute(
            select(SchoolPlanRow11)
            .where(SchoolPlanRow11.school_plan_id == plan_id)
            .options(selectinload(SchoolPlanRow11.role_assignments))
        )
    ).scalars().all()

    return render(
        templates,
        request,
        "planning/school/plan_view.html",
        {
            "user": user,
            "plan": plan,
            "template_directions": tds,
            "rows11": rows11,  # 👈 добавили
            "MONTH_NAMES": MONTH_NAMES,
        },
    )


@router.get("/{plan_id}/direction/{direction_id}", name="school_direction_edit")
async def school_direction_edit(
        request: Request,
        plan_id: int,
        direction_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)
    plan = await _get_plan_or_404(db, plan_id=plan_id, school_id=school_id)

    dto = await SchoolPlanEditService.get_direction_data(
        db, plan_id=plan_id, direction_id=direction_id, user=user
    )

    row_months_map: dict[int, list[int]] = {}
    row_roles_map: dict[int, list[str]] = {}
    row_required_docs_map: dict[int, list[str]] = {}
    row_review_places_map: dict[int, list[str]] = {}

    for r in dto.rows11:
        pv = (getattr(r, "period_values", None) or "").strip()
        row_months_map[r.id] = normalize_months_text_to_list(pv) if pv else []

        row_roles_map[r.id] = [a.role.value for a in (r.role_assignments or [])]

        row_required_docs_map[r.id] = [
            x.document_type.value for x in (r.required_documents or [])
        ]

        row_review_places_map[r.id] = [
            x.review_place.value for x in (r.review_places or [])
        ]

    responsible_roles = [
        {"value": role.value, "label_kz": role.label_kz}
        for role in ResponsibleRole.__members__.values()
    ]

    return render(
        templates,
        request,
        "planning/school/direction_edit.html",
        {
            "user": user,
            "plan": plan,
            "direction_id": direction_id,
            "direction": dto.direction,
            "rows4": dto.rows4,
            "rows11": dto.rows11,
            "MONTH_NAMES": MONTH_NAMES,
            "row_months_selected": row_months_map,
            "row_roles_selected": row_roles_map,
            "RESPONSIBLE_ROLES": responsible_roles,
            "document_types": list(DocumentType),
            "review_places": list(ReviewPlace),
            "row_required_docs_map": row_required_docs_map,
            "row_review_places_map": row_review_places_map,
        },
    )


# -----------------------------
# 5) Add row4 / row11
# -----------------------------
@router.post("/{plan_id}/direction/{direction_id}/rows4/add")
async def school_add_row4(
        plan_id: int,
        direction_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    # план проверять здесь необязательно (add_row проверит по school_id),
    # но чтобы сообщение было "План не найден" и URL не светил — оставляем прежнюю логику
    school_id = _require_school_id(user)
    await _get_plan_or_404(db, plan_id=plan_id, school_id=school_id)

    await SchoolRowsService.add_row(
        db,
        school_plan_id=plan_id,
        direction_id=direction_id,
        kind="row4",
        school_id=school_id,
    )

    return RedirectResponse(
        url=f"/planning/school/{plan_id}/direction/{direction_id}",
        status_code=303,
    )


@router.post("/{plan_id}/direction/{direction_id}/rows11/add")
async def school_add_row11(
        plan_id: int,
        direction_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)
    await _get_plan_or_404(db, plan_id=plan_id, school_id=school_id)

    await SchoolRowsService.add_row(
        db,
        school_plan_id=plan_id,
        direction_id=direction_id,
        kind="row11",
        school_id=school_id,
    )

    return RedirectResponse(
        url=f"/planning/school/{plan_id}/direction/{direction_id}",
        status_code=303,
    )


# -----------------------------
# 6) Update period + responsible (one modal)
# -----------------------------
@router.post("/{plan_id}/direction/{direction_id}/rows11/{row_id}/meta")
async def school_row11_update_meta_web(
        request: Request,
        plan_id: int,
        direction_id: int,
        row_id: int,

        # PERIOD
        period_type: str = Form(...),
        month: int | None = Form(None),
        period_values: str | None = Form(None),

        # ✅ MULTI RESPONSIBLE (чекбоксы с name="responsible_roles_cb")
        responsible_roles_cb: list[str] = Form([]),

        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    # ✅ уже список, ничего парсить не надо
    roles_list: list[str] = [str(x) for x in (responsible_roles_cb or []) if x]

    try:
        row = await SchoolRowsService.update_row11_meta(
            db,
            row_id=row_id,
            period_type=period_type,
            month=month,
            period_values=period_values,
            responsible_roles=roles_list,  # ✅ напрямую
            user=user,
        )
    except Exception:
        await db.rollback()
        raise

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if is_ajax:
        from app.modules.planning.enums import ResponsibleRole

        role_vals = [ra.role.value for ra in (row.role_assignments or [])]

        labels_map = {
            cast(ResponsibleRole, rr).value: cast(ResponsibleRole, rr).label_kz
            for rr in ResponsibleRole.__members__.values()
        }

        return {
            "ok": True,
            "row_id": row_id,
            "period_type": row.period_type.value if row.period_type else None,
            "period_value_int": row.period_value_int,
            "period_values": row.period_values,
            "responsible_roles": role_vals,
            "responsible_labels_kz": labels_map,
        }

    return RedirectResponse(
        url=f"/planning/school/{plan_id}/direction/{direction_id}",
        status_code=303,
    )


# -----------------------------
# 7) Delete rows_11, rows_11
# -----------------------------
@router.post("/{plan_id}/direction/{direction_id}/rows4/{row_id}/delete")
async def school_delete_row4(
        plan_id: int,
        direction_id: int,
        row_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)
    await _get_plan_or_404(db, plan_id=plan_id, school_id=school_id)

    row = (await db.execute(
        select(SchoolPlanRow4).where(
            SchoolPlanRow4.id == row_id,
            SchoolPlanRow4.school_plan_id == plan_id,
            SchoolPlanRow4.direction_id == direction_id,
        )
    )).scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="Строка не найдена")

    if not row.is_custom:
        raise HTTPException(status_code=403, detail="Нельзя удалить строку из шаблона")

    await db.execute(delete(SchoolPlanRow4).where(SchoolPlanRow4.id == row_id))
    await db.commit()

    return RedirectResponse(url=f"/planning/school/{plan_id}/direction/{direction_id}", status_code=303)


@router.post("/{plan_id}/direction/{direction_id}/rows11/{row_id}/delete")
async def school_delete_row11(
        plan_id: int,
        direction_id: int,
        row_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)
    await _get_plan_or_404(db, plan_id=plan_id, school_id=school_id)

    row = (await db.execute(
        select(SchoolPlanRow11).where(
            SchoolPlanRow11.id == row_id,
            SchoolPlanRow11.school_plan_id == plan_id,
            SchoolPlanRow11.direction_id == direction_id,
        )
    )).scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="Строка не найдена")

    if not row.is_custom:
        raise HTTPException(status_code=403, detail="Нельзя удалить строку из шаблона")

    await db.execute(delete(SchoolPlanRow11).where(SchoolPlanRow11.id == row_id))
    await db.commit()

    return RedirectResponse(url=f"/planning/school/{plan_id}/direction/{direction_id}", status_code=303)


# -----------------------------
# 7) Save direction
# -----------------------------
@router.post("/{plan_id}/direction/{direction_id}/save")
async def school_save_direction(
        request: Request,
        plan_id: int,
        direction_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)
    await _get_plan_or_404(db, plan_id=plan_id, school_id=school_id)

    form = await request.form()

    await SchoolPlanEditService.save_rows4(
        db, plan_id=plan_id, direction_id=direction_id, form=form, user=user
    )
    await SchoolPlanEditService.save_rows11(
        db, plan_id=plan_id, direction_id=direction_id, form=form, user=user
    )

    return RedirectResponse(
        url=f"/planning/school/{plan_id}/direction/{direction_id}",
        status_code=303,
    )


# -----------------------------
# 8) Preview / PDF
# -----------------------------
def build_role_labels_kz() -> dict[str, str]:
    # у ResponsibleRole есть label_kz
    return {role.value: role.label_kz for role in ResponsibleRole.__members__.values()}


@router.get("/{plan_id}/preview", name="school_plan_preview", response_class=HTMLResponse)
async def school_plan_preview(
        request: Request,
        plan_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    dto = await SchoolPlanExportService.get_full_plan(db, school_plan_id=plan_id, user=user)
    if not dto:
        raise HTTPException(status_code=404, detail="План не найден")

    return render(
        templates,
        request,
        "planning/school/plan_preview.html",
        {
            "user": user,
            "plan": dto.plan,
            "directions": dto.directions,
            "meta": dto.meta,
            "MONTH_NAMES": MONTH_NAMES,  # месяцы
            "ROLE_LABELS": build_role_labels_kz(),  # роли (человеческие подписи)
        },
    )


@router.get("/{plan_id}/pdf", name="school_plan_pdf", response_class=Response)
async def school_plan_pdf(
        plan_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    dto = await SchoolPlanExportService.get_full_plan(db, school_plan_id=plan_id, user=user)
    if not dto:
        raise HTTPException(status_code=404, detail="План не найден")

    meta = ApprovalMeta(
        district_name=dto.meta.district_name,
        school_name=dto.meta.school_name,
        director_fio=dto.meta.director_fio,
        director_position="Директор школы",
        approve_title="УТВЕРЖДАЮ",
    )
    pdf_bytes = PlanVshkPdf.build(dto, meta=meta)

    filename = f"plan_vshk_{dto.plan.academic_year}_{dto.plan.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# -----------------------------
# 9) Activate plan
# -----------------------------
@router.post("/{plan_id}/activate", name="school_plan_activate")
async def school_plan_activate(
        request: Request,
        plan_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = _require_school_id(user)

    await _get_plan_or_404(db, plan_id=plan_id, school_id=school_id)

    await SchoolPlanningRepo.activate_plan(
        db,
        plan_id=plan_id,
        school_id=school_id,
    )

    return RedirectResponse(
        request.url_for("school_plan_view", plan_id=plan_id),
        status_code=303,
    )


@router.post(
    "/{plan_id}/direction/{direction_id}/rows11/{row11_id}/documents",
    name="school_row11_documents_update",
)
async def school_row11_documents_update(
        request: Request,
        plan_id: int,
        direction_id: int,
        row11_id: int,
        required_document_types: list[str] = Form(default=[]),
        db: AsyncSession = Depends(get_db),
        _user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    row = await SchoolPlanningRepo.get_row11(db, row_id=row11_id)
    if not row:
        raise HTTPException(status_code=404, detail="Жол табылмады")

    await SchoolPlanEditService.save_row11_required_documents(
        db,
        row11_id=row11_id,
        document_type_values=required_document_types,
    )
    await db.commit()

    return RedirectResponse(
        url=request.url_for(
            "school_direction_edit",
            plan_id=plan_id,
            direction_id=direction_id,
        ),
        status_code=303,
    )


@router.post(
    "/{plan_id}/direction/{direction_id}/rows11/{row11_id}/review-places",
    name="school_row11_review_places_update",
)
async def school_row11_review_places_update(
        request: Request,
        plan_id: int,
        direction_id: int,
        row11_id: int,
        review_places: list[str] = Form(default=[]),
        db: AsyncSession = Depends(get_db),
        _user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    row = await SchoolPlanningRepo.get_row11(db, row_id=row11_id)
    if not row:
        raise HTTPException(status_code=404, detail="Жол табылмады")

    await SchoolPlanEditService.save_row11_review_places(
        db,
        row11_id=row11_id,
        review_place_values=review_places,
    )
    await db.commit()

    return RedirectResponse(
        url=request.url_for(
            "school_direction_edit",
            plan_id=plan_id,
            direction_id=direction_id,
        ),
        status_code=303,
    )


# обновление данных из модального окна: место рассмотрения
@router.post(
    "/{plan_id}/direction/{direction_id}/rows11/{row11_id}/review-places",
    name="school_row11_review_places_update",
)
async def school_row11_review_places_update(
        plan_id: int,
        direction_id: int,
        row11_id: int,
        review_places: list[str] = Form(default=[]),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    try:
        school_id = _require_school_id(user)

        await _get_plan_or_404(db, plan_id=plan_id, school_id=school_id)

        row = await SchoolPlanningRepo.get_row11(db, row_id=row11_id)
        if not row or row.direction_id != direction_id:
            raise HTTPException(status_code=404)

        await SchoolRowsService.save_row11_requirements(
            db,
            row11_id=row11_id,
            document_types=None,
            review_places=review_places,
        )
        await db.commit()

        return JSONResponse({
            "status": "ok",
            "review_places": review_places,
            "review_items": enum_items(ReviewPlace, review_places),
        })

    except Exception as e:
        traceback.print_exc()
        return JSONResponse({
            "status": "error",
            "message": str(e),
        }, status_code=500)


# обновление данных из модального окна: тип документов
@router.post(
    "/{plan_id}/direction/{direction_id}/rows11/{row11_id}/documents",
    name="school_row11_documents_update",
)
async def school_row11_documents_update(
        plan_id: int,
        direction_id: int,
        row11_id: int,
        required_document_types: list[str] = Form(default=[]),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    try:
        school_id = _require_school_id(user)

        await _get_plan_or_404(db, plan_id=plan_id, school_id=school_id)

        row = await SchoolPlanningRepo.get_row11(db, row_id=row11_id)
        if not row or row.direction_id != direction_id:
            raise HTTPException(status_code=404)

        await SchoolRowsService.save_row11_requirements(
            db,
            row11_id=row11_id,
            document_types=required_document_types,
            review_places=None,
        )
        await db.commit()

        return JSONResponse({
            "status": "ok",
            "documents": required_document_types,
            "document_items": enum_items(DocumentType, required_document_types),
        })

    except Exception as e:
        traceback.print_exc()
        return JSONResponse({
            "status": "error",
            "message": str(e),
        }, status_code=500)
