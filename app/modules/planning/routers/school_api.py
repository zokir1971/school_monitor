# app/modules/planning/routers/school_api.py
from typing import Callable, Awaitable, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.planning.schemas import Row11MetaUpdateIn, Row11ResponsibleUpdateIn, Row11PeriodUpdateIn
from app.modules.planning.services.school_monthly_service import MonthCalendarService
from app.modules.planning.services.school_service import SchoolRowsService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole

router = APIRouter(tags=["Planning.School.API"])


# =========================================================
# DTO
# =========================================================

class CellUpdateIn(BaseModel):
    school_plan_id: int
    direction_id: int
    kind: str  # "row4" | "row11"
    row_id: int
    field: str
    value: str | None = None


class RowAddIn(BaseModel):
    school_plan_id: int
    direction_id: int
    kind: str  # "row4" | "row11"


# =========================================================
# ADD ROW
# =========================================================

@router.post("/api/rows/add")
async def school_rows_add(
        payload: RowAddIn,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    if payload.kind not in ("row4", "row11"):
        raise HTTPException(status_code=400, detail="Invalid kind")

    res = await SchoolRowsService.add_row(
        db,
        school_plan_id=payload.school_plan_id,
        direction_id=payload.direction_id,
        kind=payload.kind,
        school_id=user.school_id,
    )
    return {"id": res.id}


# =========================================================
# UPDATE CELL
# =========================================================

@router.post("/api/cell")
async def api_cell_update(
        payload: CellUpdateIn,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN, UserRole.SUPERUSER)),
):
    if payload.kind not in ("row4", "row11"):
        raise HTTPException(status_code=400, detail="Invalid kind")

    try:
        await SchoolRowsService.update_cell(
            db,
            user=user,
            kind=payload.kind,
            row_id=payload.row_id,
            field=payload.field,
            value=payload.value,
            school_plan_id=payload.school_plan_id,
            direction_id=payload.direction_id,
        )
    except HTTPException:
        # ✅ это наша ошибка — rollback не обязателен, но безопасно
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise

    return {"ok": True}


def row11_meta_out(row) -> dict:
    roles = []
    labels_kz = []

    for a in (row.role_assignments or []):
        # a: SchoolPlanRow11Responsible
        roles.append(a.role.value)
        labels_kz.append(a.role.label_kz)

    return {
        "row_id": row.id,
        "period_type": row.period_type.value if row.period_type else None,
        "period_value_int": row.period_value_int,
        "period_values": row.period_values,

        # ✅ multi roles
        "responsible_roles": roles,  # ["director", "methodist", ...]
        "responsible_labels_kz": labels_kz,  # ["Директор", "Әдіскер", ...]
    }


async def run_with_rollback(db: AsyncSession, fn: Callable[[], Awaitable[Any]]):
    try:
        return await fn()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise


# =========================================================
# UPDATE META (PERIOD + RESPONSIBLE) ✅ НОВЫЙ ОСНОВНОЙ
# =========================================================
@router.post("/api/rows11/{row_id}/meta")
async def api_row11_update_meta(
        row_id: int,
        payload: Row11MetaUpdateIn,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN, UserRole.SUPERUSER)),
):
    row = await run_with_rollback(db, lambda: SchoolRowsService.update_row11_meta(
        db,
        user=user,
        row_id=row_id,
        period_type=payload.period_type,
        month=payload.month,
        period_values=payload.period_values,
        responsible_role=payload.responsible_role,
    ))

    return {"ok": True, **row11_meta_out(row)}


# =========================================================
# UPDATE PERIOD (legacy / compatibility)
# =========================================================
@router.post("/api/rows11/{row_id}/period")
async def api_row11_update_period(
        row_id: int,
        payload: Row11PeriodUpdateIn,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN, UserRole.SUPERUSER)),
):
    row = await run_with_rollback(db, lambda: SchoolRowsService.update_row11_meta(
        db,
        user=user,
        row_id=row_id,
        period_type=payload.period_type,
        month=payload.month,
        period_values=payload.period_values,
        responsible_role=None,  # не меняем роль
    ))

    # можно вернуть только период, но можно и всё — фронту часто удобнее всё
    out = row11_meta_out(row)
    return {
        "ok": True,
        "row_id": out["row_id"],
        "period_type": out["period_type"],
        "period_value_int": out["period_value_int"],
        "period_values": out["period_values"],
    }


# =========================================================
# UPDATE RESPONSIBLE ROLE (legacy / compatibility)
# =========================================================
@router.post("/api/rows11/{row_id}/responsible-role")
async def api_row11_update_responsible_role(
        row_id: int,
        payload: Row11ResponsibleUpdateIn,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SCHOOL_ADMIN, UserRole.SUPERUSER)),
):
    # ✅ Тут НЕ вызываем update_row11_meta, потому что он требует period_type
    row = await run_with_rollback(db, lambda: SchoolRowsService.update_row11_responsible(
        db,
        user=user,
        row_id=row_id,
        responsible_role=payload.responsible_role,
    ))

    out = row11_meta_out(row)
    return {"ok": True, "row_id": out["row_id"], "responsible_role": out["responsible_role"],
            "responsible_label_kz": out["responsible_label_kz"]}


# календарь
@router.get("/month-plans/{month_plan_id}/weeks", name="school_month_plan_weeks")
async def school_month_plan_weeks(
        month_plan_id: int,
        db: AsyncSession = Depends(get_db),
):
    """
    Получить календарные недели месяца (Пн-Вс)
    """
    return await MonthCalendarService.get_plan_weeks(
        db,
        month_plan_id=month_plan_id
    )


@router.patch("/month-items/{item_id}/assign-week", name="school_month_item_assign_week")
async def school_month_item_assign_week(
        item_id: int,
        week_of_month: int,
        db: AsyncSession = Depends(get_db),
):
    """
    Назначить неделю задаче
    """
    await MonthCalendarService.assign_week_to_item(
        db,
        item_id=item_id,
        week_of_month=week_of_month
    )

    return {"ok": True}


@router.patch("/month-plans/{month_plan_id}/bulk-assign-week")
async def school_month_items_bulk_assign_week(
        month_plan_id: int,
        week_of_month: int,
        item_ids: list[int],
        db: AsyncSession = Depends(get_db),
):
    return await MonthCalendarService.bulk_assign_week(
        db,
        month_plan_id=month_plan_id,
        item_ids=item_ids,
        week_of_month=week_of_month
    )
