# app/routers/web/planning/school_monthly_web.py

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Form, Request, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.responses import HTMLResponse, RedirectResponse

from app.db.session import get_db
from app.modules.planning.enums import PlanStatus, ResponsibleRole
from app.modules.planning.repo_monthly import ACADEMIC_MONTHS
from app.modules.planning.repo_monthly import SchoolMonthlyPlanRepo, MonthItemUpdate
from app.modules.planning.ropo_month_plan_assignee import SchoolMonthPlanAssigneeRepo
from app.modules.planning.services.monthly_plan_dto_service import SchoolMonthPlanAssigneeService
from app.modules.planning.services.school_monthly_service import SchoolMonthlyPlanningService
from app.modules.users.deps import require_roles
from app.modules.users.models import UserRole, User  # поправь если у тебя UserRole в другом месте
from app.modules.staff.utils.staff_require_school import require_school_id
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates
from app.utils.calendar_weeks import calc_year_from_academic, month_weeks_grid

router = APIRouter(prefix="/planning/school", tags=["planning-school-web"])

# --- Месяцы для выпадающего списка ---
MONTH_LABELS = {
    8: "Тамыз (Август)",
    9: "Қыркүйек (Сентябрь)",
    10: "Қазан (Октябрь)",
    11: "Қараша (Ноябрь)",
    12: "Желтоқсан (Декабрь)",
    1: "Қаңтар (Январь)",
    2: "Ақпан (Февраль)",
    3: "Наурыз (Март)",
    4: "Сәуір (Апрель)",
    5: "Мамыр (Май)",
    6: "Мауысым (Июнь)"
}


def _months_list() -> list[dict[str, Any]]:
    return [{"num": m, "label": MONTH_LABELS.get(m, str(m))} for m in ACADEMIC_MONTHS]


def _group_items_by_direction(items):
    """
    Группирует элементы месячного плана по направлению.

    Args:
        items: list[SchoolMonthPlanItem]
            Желательно, чтобы source_row11 и source_row11.direction были заранее подгружены.

    Returns:
        list[dict]:
            [
                {
                    "direction_id": int,
                    "direction": PlanDirection | None,
                    "items": list[SchoolMonthPlanItem],
                },
                ...
            ]
    """

    grouped: dict[int, dict[str, Any]] = {}

    for item in items:
        src = getattr(item, "source_row11", None)
        direction = getattr(src, "direction", None) if src else None
        direction_id = getattr(src, "direction_id", None) if src else None
        direction_id = direction_id or 0

        if direction_id not in grouped:
            grouped[direction_id] = {
                "direction_id": direction_id,
                "direction": direction,
                "items": [],
            }

        grouped[direction_id]["items"].append(item)

    def _sort_key(entry: dict[str, Any]):
        direction_obj = entry.get("direction")

        if direction_obj is not None:
            sort_order = getattr(direction_obj, "sort_order", None)
            direction_obj_id = getattr(direction_obj, "id", 0)

            if sort_order is not None:
                return sort_order, direction_obj_id

        return 9999, entry.get("direction_id", 0)

    return sorted(grouped.values(), key=_sort_key)


@router.get("/monthly", name="school_monthly_page", response_class=HTMLResponse)
async def school_monthly_page(
        request: Request,
        month: int | None = Query(default=None),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    months = _months_list()

    review_place_labels = {
        "ped_council": "Пед.кеңес",
        "method_council": "Әд.кеңес",
        "director_council": "ДЖ.кеңес",
        "administrative_council": "Әк.кеңес",
        "method_assoc": "ӘБ.отырысы",
    }

    if not getattr(user, "school_id", None):
        raise HTTPException(status_code=400, detail="У пользователя не задана school_id")

    active_plan = await SchoolMonthlyPlanRepo.get_active_school_plan(
        db,
        school_id=user.school_id
    )

    if not active_plan:
        return render(
            templates,
            request,
            "planning/school/monthly_tasks.html",
            {
                "user": user,
                "months": months,
                "month": month,
                "active_plan": None,
                "month_plan": None,
                "blocks": [],
                "weeks": [],
                "error": "Нет активного годового плана. Сначала активируйте годовой план.",
                "can_build": False,
                "open_month_plan_id": None,
                "review_place_labels": review_place_labels,
            },
        )

    if month is None:
        return render(
            templates,
            request,
            "planning/school/monthly_tasks.html",
            {
                "user": user,
                "months": months,
                "month": None,
                "active_plan": active_plan,
                "month_plan": None,
                "blocks": [],
                "weeks": [],
                "info": "Выберите месяц и нажмите «Открыть».",
                "can_build": False,
                "open_month_plan_id": None,
                "review_place_labels": review_place_labels,
            },
        )

    year = calc_year_from_academic(active_plan.academic_year, month)

    month_plan = await SchoolMonthlyPlanRepo.get_month_plan(
        db,
        school_plan_id=active_plan.id,
        year=year,
        month=month,
    )

    blocks = []

    if month_plan:
        items = await SchoolMonthlyPlanRepo.list_items(
            db,
            month_plan_id=month_plan.id,
            with_source=True,
        )

        # ===== ОТЛАДКА review_places =====
        for it in items:
            print("=" * 80)
            print("ITEM ID:", getattr(it, "id", None))
            print("ITEM TYPE:", type(it))

            item_places = getattr(it, "review_places", None)
            print("ITEM review_places:", item_places)

            if item_places:
                for rp in item_places:
                    print("  ITEM RP OBJ:", rp)
                    print("  ITEM RP DICT:", getattr(rp, "__dict__", {}))

            src = getattr(it, "source_row11", None)
            print("SOURCE_ROW11:", src)
            print("SOURCE_ROW11 ID:", getattr(src, "id", None) if src else None)

            src_places = getattr(src, "review_places", None) if src else None
            print("SRC review_places:", src_places)

            if src_places:
                for rp in src_places:
                    print("  SRC RP OBJ:", rp)
                    print("  SRC RP DICT:", getattr(rp, "__dict__", {}))
        # ===== /ОТЛАДКА review_places =====

        blocks = _group_items_by_direction(items)

    weeks = month_weeks_grid(year, month)

    return render(
        templates,
        request,
        "planning/school/monthly_tasks.html",
        {
            "user": user,
            "months": months,
            "month": month,
            "active_plan": active_plan,
            "month_plan": month_plan,
            "blocks": blocks,
            "weeks": weeks,
            "can_build": month_plan is None,
            "open_month_plan_id": month_plan.id if month_plan else None,
            "review_place_labels": review_place_labels,
        },
    )


MONTH_NAMES = {
    1: "Қаңтар", 2: "Ақпан", 3: "Наурыз", 4: "Сәуір",
    5: "Мамыр", 6: "Маусым", 7: "Шілде", 8: "Тамыз",
    9: "Қыркүйек", 10: "Қазан", 11: "Қараша", 12: "Желтоқсан",
}


@router.post("/monthly/{month}/draft", name="school_monthly_build_draft")
async def school_monthly_build_draft(
        request: Request,
        month: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    if not getattr(user, "school_id", None):
        raise HTTPException(status_code=400, detail="У пользователя не задана school_id")

    active_plan = await SchoolMonthlyPlanRepo.get_active_school_plan(db, school_id=user.school_id)
    if not active_plan:
        raise HTTPException(status_code=400, detail="Нет активного годового плана")

    # ✅ вычисляем год по учебному году
    year = calc_year_from_academic(active_plan.academic_year, month)

    # ✅ создаём/берём черновик (ВАЖНО: передай year в сервис, если он у тебя обязателен)
    month_plan = await SchoolMonthlyPlanningService.get_or_create_draft(
        db,
        school_id=user.school_id,
        school_plan_id=active_plan.id,
        year=year,  # ⭐ добавь, если сервис принимает
        month=month,
    )
    await db.commit()

    # ✅ недели считаем уже от фактического month_plan
    weeks = month_weeks_grid(month_plan.year, month_plan.month)

    months = _months_list()
    role_labels = {r.value: getattr(r, "label_kz", r.value) for r in ResponsibleRole}
    print("MONTH_PLAN:", month_plan)
    print("YEAR:", month_plan.year if month_plan else None)
    print("MONTH:", month_plan.month if month_plan else None)
    print("WEEKS:", weeks)
    return render(
        templates,
        request,
        "planning/school/monthly_tasks.html",
        {
            "request": request,  # ⭐ важно
            "user": user,
            "weeks": weeks,  # ⭐ чтобы селектор не был пустой
            "months": months,
            "month": month,
            "active_plan": active_plan,
            "month_plan": month_plan,  # ⭐ НЕ None
            "MONTH_NAMES": MONTH_NAMES,
            "role_labels": role_labels,
            "blocks": [],  # если хочешь сразу показать таблицу — лучше blocks посчитать
            "success": "Черновик сформирован. Нажмите «Открыть».",
            "can_build": False,
        },
    )


@router.post("/monthly/{month}/save", name="school_monthly_save_draft")
async def school_monthly_save_draft(
        request: Request,
        month: int,
        month_plan_id: int = Form(...),
        school_plan_id: int = Form(...),
        item_ids: list[int] = Form(default=[]),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    months = _months_list()

    if not getattr(user, "school_id", None):
        raise HTTPException(status_code=400, detail="У пользователя не задана school_id")

    form = await request.form()

    active_plan = await SchoolMonthlyPlanRepo.get_school_plan_for_school(
        db,
        school_plan_id=school_plan_id,
        school_id=user.school_id,
    )
    if not active_plan:
        raise HTTPException(status_code=400, detail="Годовой план не найден (или не принадлежит школе)")

    mp = await SchoolMonthlyPlanRepo.get_month_plan_by_id(db, month_plan_id=month_plan_id)
    if not mp:
        raise HTTPException(status_code=400, detail="Месячный план не найден")

    if mp.school_plan_id != school_plan_id or mp.month != month:
        raise HTTPException(
            status_code=400,
            detail="Некорректные параметры month_plan (план не соответствует school_plan_id/месяцу)",
        )

    mp_status = mp.status.value if hasattr(mp.status, "value") else mp.status
    if mp_status != PlanStatus.DRAFT.value:
        raise HTTPException(status_code=400, detail="Сохранение доступно только в статусе 'Черновик'")

    weeks = month_weeks_grid(mp.year, mp.month)
    week_map = {w.week: w for w in weeks}

    updates: list[MonthItemUpdate] = []
    for item_id in item_ids:
        is_included = form.get(f"item_{item_id}_included") == "1"

        week_raw = (form.get(f"item_{item_id}_week") or "").strip()
        week_val = int(week_raw) if week_raw.isdigit() else None

        notes_val = (form.get(f"item_{item_id}_notes") or "").strip() or None

        planned_start_val = None
        planned_end_val = None

        if week_val is not None:
            wk = week_map.get(week_val)
            if not wk:
                raise HTTPException(
                    status_code=400,
                    detail=f"Неделя {week_val} не найдена в сетке месяца. item_id={item_id}",
                )
            planned_start_val = wk.start
            planned_end_val = wk.end

        updates.append(
            MonthItemUpdate(
                item_id=int(item_id),
                is_included=is_included,
                week_of_month=week_val,
                planned_start=planned_start_val,
                planned_end=planned_end_val,
                notes=notes_val,
            )
        )

    try:
        await SchoolMonthlyPlanRepo.upsert_item_flags_bulk(db, updates=updates)
        await db.commit()

        year = calc_year_from_academic(active_plan.academic_year, month)

        month_plan = await SchoolMonthlyPlanRepo.get_month_plan(
            db,
            school_plan_id=school_plan_id,
            year=year,
            month=month,
        )

        items = []
        blocks = []
        review_place_labels = {
            "ped_council": "Педагогикалық кеңес",
            "method_council": "Әдістемелік кеңес",
            "director_council": "Директор жанындағы кеңес",
            "administrative_council": "Әкімшілік кеңес",
            "method_assoc": "Әдістемелік бірлестік",
        }

        if month_plan:
            items = await SchoolMonthlyPlanRepo.list_items(
                db,
                month_plan_id=month_plan.id,
                with_source=True,
            )
            weeks = month_weeks_grid(month_plan.year, month_plan.month)
            blocks = _group_items_by_direction(items)

        return render(
            templates,
            request,
            "planning/school/monthly_tasks.html",
            {
                "user": user,
                "months": months,
                "month": month,
                "school_plan_id": school_plan_id,
                "active_plan": active_plan,
                "month_plan": month_plan,
                "blocks": blocks,
                "weeks": weeks,
                "review_place_labels": review_place_labels,
                "success": "Черновик сохранён.",
            },
        )

    except Exception as e:
        await db.rollback()

        year = calc_year_from_academic(active_plan.academic_year, month)

        month_plan = await SchoolMonthlyPlanRepo.get_month_plan(
            db,
            school_plan_id=school_plan_id,
            year=year,
            month=month,
        )

        items = await SchoolMonthlyPlanRepo.list_items(
            db,
            month_plan_id=month_plan.id,
            with_source=True,
        ) if month_plan else []

        weeks = month_weeks_grid(month_plan.year, month_plan.month) if month_plan else []
        blocks = _group_items_by_direction(items)

        return render(
            templates,
            request,
            "planning/school/monthly_tasks.html",
            {
                "user": user,
                "months": months,
                "month": month,
                "school_plan_id": school_plan_id,
                "active_plan": active_plan,
                "month_plan": month_plan,
                "blocks": blocks,
                "weeks": weeks,
                "error": str(e),
            },
            status_code=400,
        )


@router.post("/monthly/{month}/submit")
async def school_monthly_submit(
        request: Request,
        month: int,
        month_plan_id: int = Form(...),
        school_plan_id: int = Form(...),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    months = _months_list()

    try:
        # переводим план в ACTIVE
        await SchoolMonthlyPlanningService.submit_month_plan(
            db,
            month_plan_id=month_plan_id
        )

        month_plan = await SchoolMonthlyPlanRepo.get_month_plan_by_id(
            db,
            month_plan_id=month_plan_id
        )

        items = await SchoolMonthlyPlanRepo.list_items(
            db,
            month_plan_id=month_plan.id,
            with_source=True
        ) if month_plan else []

        blocks = _group_items_by_direction(items)

        weeks = []
        if month_plan:
            weeks = month_weeks_grid(month_plan.year, month_plan.month)

        print("MONTH_PLAN:", month_plan)
        print("YEAR:", month_plan.year if month_plan else None)
        print("MONTH:", month_plan.month if month_plan else None)
        print("WEEKS:", weeks)

        return render(
            templates,
            request,
            "planning/school/monthly_tasks.html",
            {
                "request": request,
                "user": user,
                "months": months,
                "month": month,
                "school_plan_id": school_plan_id,
                "month_plan": month_plan,
                "blocks": blocks,
                "weeks": weeks,
                "success": "План отправлен на исполнение.",
            },
        )

    except Exception as e:
        await db.rollback()

        month_plan = await SchoolMonthlyPlanRepo.get_month_plan_by_id(
            db,
            month_plan_id=month_plan_id
        )

        items = await SchoolMonthlyPlanRepo.list_items(
            db,
            month_plan_id=month_plan.id,
            with_source=True
        ) if month_plan else []

        blocks = _group_items_by_direction(items)

        weeks = []
        if month_plan:
            weeks = month_weeks_grid(month_plan.year, month_plan.month)

        print("WEEKS DEBUG:", weeks)

        return render(
            templates,
            request,
            "planning/school/monthly_tasks.html",
            {
                "request": request,
                "user": user,
                "months": months,
                "month": month,
                "school_plan_id": school_plan_id,
                "month_plan": month_plan,
                "blocks": blocks,
                "weeks": weeks,
                "error": str(e),
            },
            status_code=400,
        )


# удаления месячного плана если черновик
@router.post("/monthly/delete", name="school_monthly_delete_draft")
async def school_monthly_delete_draft(
        request: Request,
        month_plan_id: int = Form(...),
        month: int = Form(...),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    if not getattr(user, "school_id", None):
        raise HTTPException(400, "У пользователя не задана school_id")

    await SchoolMonthlyPlanningService.delete_draft_month_plan(
        db,
        month_plan_id=month_plan_id,
        school_id=user.school_id,
    )

    return RedirectResponse(
        url=f"/planning/school/monthly?month={month}",
        status_code=303
    )


# страница назначения
@router.get(
    "/monthly/{month_item_id}/assignees",
    name="school_month_item_assignees",
    response_class=HTMLResponse,
)
async def school_month_item_assignees(
        request: Request,
        month_item_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = require_school_id(user)

    dto = await SchoolMonthPlanAssigneeService.get_assignment_page_data(
        db,
        school_id=school_id,
        month_item_id=month_item_id,
    )

    if not dto:
        raise HTTPException(
            status_code=404,
            detail="Задача месячного плана не найдена",
        )

    return render(
        templates,
        request,
        "planning/school/month_item_assignees.html",  # если шаблон называется иначе — замени
        {
            "dto": dto,
            "month_item": dto.month_item,
            "row11": dto.row11,
            "direction_name": dto.direction_name,
            "topic": dto.topic,
            "goal": dto.goal,
            "week_of_month": dto.week_of_month,
            "planned_start": dto.planned_start,
            "planned_end": dto.planned_end,
            "can_assign": dto.can_assign,
            "responsible_blocks": dto.responsible_blocks,
            "selected_staff_role_ids": dto.selected_staff_role_ids,
        },
    )


@router.post(
    "/monthly/{month_item_id}/assignees",
    name="school_month_item_assignees_save",
)
async def school_month_item_assignees_save(
        request: Request,
        month_item_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    school_id = require_school_id(user)

    form = await request.form()
    raw_ids = form.getlist("assignee_ids")

    selected_staff_role_ids: list[int] = []
    for x in raw_ids:
        s = str(x).strip()
        if s.isdigit():
            selected_staff_role_ids.append(int(s))

    ok = await SchoolMonthPlanAssigneeService.save_assignments(
        db,
        school_id=school_id,
        month_item_id=month_item_id,
        selected_staff_role_ids=selected_staff_role_ids,
        assigned_by_user_id=user.id,
    )

    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Задача месячного плана не найдена",
        )

    await db.commit()

    item = await SchoolMonthPlanAssigneeRepo.get_month_item_with_row11(
        db,
        month_item_id=month_item_id,
    )
    if not item:
        raise HTTPException(
            status_code=404,
            detail="Задача месячного плана не найдена",
        )

    base_url = request.url_for("school_monthly_page")

    return RedirectResponse(
        url=f"{base_url}?month={item.month_plan.month}&school_plan_id={item.month_plan.school_plan_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
