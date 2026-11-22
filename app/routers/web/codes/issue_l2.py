from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.routers.web.helpers import code_issue

router = APIRouter()

@router.get("/l1/issue-l2")
async def l1_issue_l2_page(request: Request, db: AsyncSession = Depends(get_db), user=Depends(require_roles(UserRole.REGION_ADMIN))):
    return await code_issue.page(request, db, user, "L2")

@router.post("/l1/issue-l2")
async def l1_issue_l2_submit(request: Request, district_ids: list[int] = Form(default_factory=list), quota_total: int = Form(1),
        db: AsyncSession = Depends(get_db), user=Depends(require_roles(UserRole.REGION_ADMIN))):
    return await code_issue.submit(request, db, user, "L2", district_ids, quota_total)

@router.get("/l1/issue-l2/result/{batch_id}")
async def l1_issue_l2_result(request: Request, batch_id: str, current_user=Depends(require_roles(UserRole.REGION_ADMIN))):
    return await code_issue.result(request, current_user, "L2", batch_id)

@router.get("/l1/issue-l2/pdf/{batch_id}")
async def l1_issue_l2_pdf(request: Request, batch_id: str, _user=Depends(require_roles(UserRole.REGION_ADMIN))):
    return await code_issue.pdf(request, _user, "L2", batch_id)
