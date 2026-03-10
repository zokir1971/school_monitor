# app/routers/web/planning/__init__.py

from fastapi import APIRouter

from .superuser_web import router as superuser_web_router
from .school_web import router as school_web_router
from .school_monthly_web import router as school_monthly_web_router


router = APIRouter()

router.include_router(superuser_web_router)
router.include_router(school_web_router)
router.include_router(school_monthly_web_router)
