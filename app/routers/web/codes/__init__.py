# app/routers/web/codes/__init__.py

from fastapi import APIRouter

from .issue_l1 import router as issue_l1_router
from .issue_l2 import router as issue_l2_router
from .issue_l3 import router as issue_l3_router

router = APIRouter()

router.include_router(issue_l1_router)
router.include_router(issue_l2_router)
router.include_router(issue_l3_router)

