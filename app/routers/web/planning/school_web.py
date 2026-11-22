# app/routers/web/planning/school_web.py
from __future__ import annotations
from app.core.planning_profile import measure_export_phase

from app.modules.planning.services.direction_sample_service import load_direction_samples

from typing import cast

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload
from starlette.responses import HTMLResponse, RedirectResponse

from app.db.session import get_db
from app.modules.org.models import School
from app.modules.planning.enums import PlanStatus, ResponsibleRole, ReviewPlace
from app.modules.planning.models_school import SchoolPlan, SchoolPlanRow11, SchoolPlanRow4
from app.modules.planning.repositories.school_plan_repository import SchoolPlanningRepo
from app.modules.planning.schemas.school_plan_row11_schemas import SchoolPlanRow11UpdateDTO
from app.modules.planning.services.plan_export_service import SchoolPlanExportService
from app.modules.planning.services.school_plan_service import (
    SchoolPlanEditService,
    SchoolPlanningService,
    SchoolRowsService,
)
from app.modules.planning.validators import normalize_months_text_to_list
from app.modules.reports.enums import DocumentType
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates
from app.utils.plan_vshk_pdf import ApprovalMeta
from app.modules.planning.utils.plan_pdf_worker import (
    PdfQueueBusy, PdfWorkerUnavailable, build_plan_pdf, snapshot_plan_pdf,
)

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
    school = await db.get(School, school_id, options=[raiseload("*")])
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


def _pick_active_plan(
        plans: list[SchoolPlan],
) -> SchoolPlan | None:
    """
    Возвращает текущий рабочий план школы.

    Приоритет:
    1. ACTIVE
    2. DRAFT
    """

    for plan in plans:
        if plan.status == PlanStatus.ACTIVE:
            return plan

    for plan in plans:
        if plan.status == PlanStatus.DRAFT:
            return plan

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
@router.get(
    "/",
    name="school_dashboard",
)
async def school_dashboard(
        request: Request,
        academic_year: str | None = None,
        tab: str | None = None,
        db: AsyncSession = Depends(get_db),
        user=Depends(
            require_roles(UserRole.SCHOOL_ADMIN)
        ),
):
    """
    Главная страница годовых планов ВШК школы.

    Если academic_year передан в URL — показываем выбранный год.

    Если academic_year не передан:
    1. используем год ACTIVE-плана;
    2. если ACTIVE нет — год DRAFT-плана;
    3. если планов нет — fallback из _normalize_academic_year().
    """

    tab_val = _normalize_tab(tab)

    # =====================================================
    # SCHOOL
    # =====================================================

    school_id = _require_school_id(user)

    school = await _get_school_or_400(
        db,
        school_id=school_id,
    )

    # =====================================================
    # TEMPLATES
    # =====================================================

    templates_active = (
        await SchoolPlanningRepo.list_active_templates(
            db
        )
    )

    active_template_id = (
        templates_active[0].id
        if templates_active
        else None
    )

    # =====================================================
    # ACADEMIC YEAR
    # =====================================================

    requested_year = (academic_year or "").strip()

    if requested_year:
        year = requested_year
        all_plans = await SchoolPlanningRepo.list_school_plans(
            db, school_id=school_id, academic_year=year,
        )
    else:
        # Reuse this one ordered result for choosing the year, the active plan
        # and the visible tab. Do not read the same plans a second/third time.
        school_plans = await SchoolPlanningRepo.list_school_plans(
            db, school_id=school_id,
        )
        current_plan = _pick_active_plan(school_plans)
        year = current_plan.academic_year if current_plan is not None else _normalize_academic_year(None)
        all_plans = [plan for plan in school_plans if plan.academic_year == year]

    active_plan = _pick_active_plan(all_plans)
    status_filter = {
        "active": PlanStatus.ACTIVE,
        "archive": PlanStatus.ARCHIVED,
    }.get(tab_val)
    plans = (all_plans if status_filter is None else
             [plan for plan in all_plans if plan.status == status_filter.value])

    # =====================================================
    # RENDER
    # =====================================================

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

    return render(
        templates,
        request,
        "planning/school/plan_view.html",
        {
            "user": user,
            "plan": plan,
            "template_directions": tds,
            "MONTH_NAMES": MONTH_NAMES,
        },
    )


@router.get(
    "/{plan_id}/direction/{direction_id}",
    name="school_direction_edit",
)
async def school_direction_edit(
        request: Request,
        plan_id: int,
        direction_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    """
    Страница направления годового плана ВШК.

    Показывает:
    - строки направления;
    - период выполнения;
    - места рассмотрения;
    - итоговые документы.

    Редактирование строки row11 выполняется
    на отдельной странице.
    """

    school_id = _require_school_id(user)

    plan = await _get_plan_or_404(
        db,
        plan_id=plan_id,
        school_id=school_id,
    )

    dto = await SchoolPlanEditService.get_direction_data(
        db,
        plan_id=plan_id,
        direction_id=direction_id,
        user=user,
    )

    # =====================================================
    # Данные для read-only отображения rows11
    # =====================================================

    template_samples = await load_direction_samples(
        db, template_id=plan.template_id, direction_id=direction_id, rows=dto.rows11,
    )

    row_months_map: dict[int, list[int]] = {}
    row_required_docs_map: dict[int, list[str]] = {}
    row_review_places_map: dict[int, list[str]] = {}

    for row in dto.rows11:
        period_values = (
                getattr(row, "period_values", None) or ""
        ).strip()

        row_months_map[row.id] = (
            normalize_months_text_to_list(period_values)
            if period_values
            else []
        )

        row_required_docs_map[row.id] = [
            item.document_type.value
            for item in (row.required_documents or [])
        ]

        row_review_places_map[row.id] = [
            item.review_place.value
            for item in (row.review_places or [])
        ]

    # =====================================================
    # Render
    # =====================================================

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

            # Период
            "MONTH_NAMES": MONTH_NAMES,
            "row_months_selected": row_months_map,
            "template_samples": template_samples,

            # Итоговые документы
            "document_types": list(DocumentType),
            "row_required_docs_map": row_required_docs_map,

            # Места рассмотрения
            "review_places": list(ReviewPlace),
            "row_review_places_map": row_review_places_map,
        },
    )


@router.get(
    "/{plan_id}/direction/{direction_id}/rows11/{row11_id}/edit",
    name="school_row11_edit",
    response_class=HTMLResponse,
)
async def school_row11_edit(
        request: Request,
        plan_id: int,
        direction_id: int,
        row11_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.SCHOOL_ADMIN)
        ),
):
    """
    Страница полного редактирования одной задачи
    годового плана ВШК.
    """

    school_id = _require_school_id(user)

    # План должен принадлежать школе пользователя.
    await _get_plan_or_404(
        db,
        plan_id=plan_id,
        school_id=school_id,
    )

    page = await SchoolPlanEditService.get_row11_edit_page(
        db,
        row11_id=row11_id,
        user=user,
    )

    # Защита от подстановки plan_id / direction_id в URL.
    if (
            page.plan_id != plan_id
            or page.direction_id != direction_id
    ):
        raise HTTPException(
            status_code=404,
            detail="Тапсырма табылмады.",
        )

    return render(
        templates,
        request,
        "planning/school/row11_edit.html",
        {
            "user": user,
            "page": page,
            "MONTH_NAMES": MONTH_NAMES,
        },
    )


@router.post(
    "/{plan_id}/direction/{direction_id}/rows11/{row11_id}/edit",
    name="school_row11_update",
)
async def school_row11_update(
        request: Request,
        plan_id: int,
        direction_id: int,
        row11_id: int,

        topic: str = Form(...),
        goal: str = Form(default=""),
        control_object: str = Form(default=""),
        control_type: str = Form(default=""),
        methods: str = Form(default=""),

        deadlines: str = Form(default=""),
        second_control: str = Form(default=""),

        period_type: str = Form(...),
        month: int | None = Form(default=None),
        period_values: str = Form(default=""),

        responsible_roles: list[str] = Form(default=[]),
        review_places: list[str] = Form(default=[]),
        required_document_types: list[str] = Form(default=[]),

        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.SCHOOL_ADMIN)
        ),
):
    """
    Полное сохранение одной задачи годового плана ВШК.
    """

    school_id = _require_school_id(user)

    await _get_plan_or_404(
        db,
        plan_id=plan_id,
        school_id=school_id,
    )

    # Сначала получаем страницу/контекст строки,
    # чтобы проверить принадлежность plan + direction.
    page = await SchoolPlanEditService.get_row11_edit_page(
        db,
        row11_id=row11_id,
        user=user,
    )

    if (
            page.plan_id != plan_id
            or page.direction_id != direction_id
    ):
        raise HTTPException(
            status_code=404,
            detail="Тапсырма табылмады.",
        )

    data = SchoolPlanRow11UpdateDTO(
        topic=topic,

        goal=goal,
        control_object=control_object,
        control_type=control_type,
        methods=methods,

        deadlines=deadlines,
        second_control=second_control,

        period_type=period_type,
        month=month,
        period_values=period_values,

        responsible_roles=responsible_roles,
        review_places=review_places,
        required_document_types=required_document_types,
    )

    try:
        await SchoolPlanEditService.update_row11(
            db,
            row11_id=row11_id,
            data=data,
            user=user,
        )

        await db.commit()

    except Exception:
        await db.rollback()
        raise

    redirect_url = request.url_for(
        "school_direction_edit",
        plan_id=plan_id,
        direction_id=direction_id,
    )

    return RedirectResponse(
        url=f"{redirect_url}#row11-{row11_id}",
        status_code=303,
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
# 6) Delete rows_11, rows_11
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
    with measure_export_phase("export_data"):
        dto = await SchoolPlanExportService.get_full_plan(db, school_plan_id=plan_id, user=user)
    if not dto:
        raise HTTPException(status_code=404, detail="План не найден")

    with measure_export_phase("preview_render"):
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
    with measure_export_phase("export_data"):
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
    document = snapshot_plan_pdf(dto)
    filename = f"plan_vshk_{document.plan.academic_year}_{document.plan.id}.pdf"
    # The export is a read-only GET. Release its transaction/connection before
    # waiting for a PDF slot; the process receives only a scalar snapshot.
    await db.close()
    try:
        with measure_export_phase("pdf_render"):
            pdf_bytes = await build_plan_pdf(document, meta=meta)
    except (PdfQueueBusy, PdfWorkerUnavailable):
        raise HTTPException(
            status_code=503,
            detail="Сервис формирования PDF временно недоступен. Повторите загрузку через несколько секунд. / "
                   "PDF дайындау қызметі уақытша қолжетімсіз. Бірнеше секундтан кейін қайталап көріңіз.",
            headers={"Retry-After": "3"},
        ) from None

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
