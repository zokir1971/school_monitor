from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.routers.web.helpers import code_issue

router = APIRouter()

@router.get("/super/issue-l1")
async def super_issue_l1_page(request: Request, db: AsyncSession = Depends(get_db), current_user=Depends(require_roles(UserRole.SUPERUSER))):
    return await code_issue.page(request, db, current_user, "L1")

@router.post("/super/issue-l1")
async def super_issue_l1_submit(request: Request, region_ids: list[int] = Form(default_factory=list), quota_total: int = Form(1),
        db: AsyncSession = Depends(get_db), current_user=Depends(require_roles(UserRole.SUPERUSER))):
    return await code_issue.submit(request, db, current_user, "L1", region_ids, quota_total)

@router.get("/super/issue-l1/result/{batch_id}")
async def super_issue_l1_result(request: Request, batch_id: str, current_user=Depends(require_roles(UserRole.SUPERUSER))):
    return await code_issue.result(request, current_user, "L1", batch_id)

@router.get("/super/issue-l1/pdf/{batch_id}")
async def super_issue_l1_pdf(request: Request, batch_id: str, _user=Depends(require_roles(UserRole.SUPERUSER))):
    return await code_issue.pdf(request, _user, "L1", batch_id)
