from fastapi import APIRouter

from .common import router as common_router
from .region import router as region_router
from .district import router as district_router
from .school import router as school_router
from .school_staff import router as teacher_router


router = APIRouter()
router.include_router(common_router)
router.include_router(region_router)
router.include_router(district_router)
router.include_router(school_router)
router.include_router(teacher_router)

