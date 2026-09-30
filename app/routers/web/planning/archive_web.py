# app/routers/web/planning/archive_web.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app.db.session import get_db
from app.modules.planning.services.archive_service import (
    PlanningArchiveService,
)
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User


router = APIRouter(
    prefix="/planning/school",
    tags=["Planning.School.Web"],
)


# =========================================================
# ARCHIVE SCHOOL PLAN
# =========================================================

@router.post(
    "/plan/{plan_id}/archive",
    name="school_plan_archive",
)
async def school_plan_archive(
        request: Request,
        plan_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.SCHOOL_ADMIN)
        ),
):
    """
    Архивирует завершённый учебный год ВШК.

    Архивируются:
        - годовой план SchoolPlan;
        - связанные месячные планы SchoolMonthPlan.

    Не изменяются:
        - статусы задач месячного плана;
        - назначения исполнителей;
        - документы;
        - отчёты;
        - PDF / QR;
        - результаты рассмотрения.

    Все бизнес-проверки выполняются
    PlanningArchiveService.
    """

    await PlanningArchiveService.archive_school_plan(
        db,
        plan_id=plan_id,
        user=user,
    )

    return RedirectResponse(
        url=request.url_for(
            "school_plan_view",
            plan_id=plan_id,
        ),
        status_code=303,
    )
