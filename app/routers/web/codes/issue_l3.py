from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.routers.web.helpers import code_issue

router = APIRouter()

@router.get("/l1/issue-l3")
@router.get("/l2/issue-l3")
async def l2_issue_l3_page(request: Request, db: AsyncSession = Depends(get_db), user=Depends(require_roles(UserRole.DISTRICT_ADMIN, UserRole.REGION_ADMIN))):
    return await code_issue.page(request, db, user, "L3")

@router.post("/l1/issue-l3")
@router.post("/l2/issue-l3")
async def l2_issue_l3_submit(request: Request, school_ids: list[int] = Form(default_factory=list), quota_total: int = Form(1),
        db: AsyncSession = Depends(get_db), user=Depends(require_roles(UserRole.DISTRICT_ADMIN, UserRole.REGION_ADMIN))):
    return await code_issue.submit(request, db, user, "L3", school_ids, quota_total)

@router.get("/l1/issue-l3/result/{batch_id}")
@router.get("/l2/issue-l3/result/{batch_id}")
async def l2_issue_l3_result(request: Request, batch_id: str, current_user=Depends(require_roles(UserRole.DISTRICT_ADMIN, UserRole.REGION_ADMIN))):
    return await code_issue.result(request, current_user, "L3", batch_id)

@router.get("/l1/issue-l3/pdf/{batch_id}")
@router.get("/l2/issue-l3/pdf/{batch_id}")
async def l2_issue_l3_pdf(request: Request, batch_id: str, _user=Depends(require_roles(UserRole.DISTRICT_ADMIN, UserRole.REGION_ADMIN))):
    return await code_issue.pdf(request, _user, "L3", batch_id)
