# app/modules/planning/routers/archive_router.py
'''
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.enums import UserRole
from app.modules.users.deps import require_roles
from app.modules.users.models import User
from app.modules.users.deps import get_db

from ..services import PlanningArchiveService


router = APIRouter(prefix="/planning/archive", tags=["planning.archive"])


@router.post("/plans/{plan_id}", response_model=dict)
async def archive_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    await PlanningArchiveService.archive_school_plan(db, plan_id=plan_id)
    await db.commit()
    return {"ok": True}
'''
