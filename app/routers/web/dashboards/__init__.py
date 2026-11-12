from fastapi import APIRouter

from .common import router as common_router
from .region import router as region_router
from .district import router as district_router
from .school import router as school_router
from .school_staff import router as school_staff_router
from .teacher import router as teacher_router
from .workspace_web import router as workspace_router
from .question_bank_expert_dashboard_web import router as question_bank_expert_dashboard_router


from .territorial_staff import router as territorial_staff_router

router = APIRouter()
router.include_router(territorial_staff_router)
router.include_router(common_router)
router.include_router(region_router)
router.include_router(district_router)
router.include_router(school_router)
router.include_router(school_staff_router)
router.include_router(teacher_router)
router.include_router(workspace_router)
router.include_router(question_bank_expert_dashboard_router)
