# app/routers/web/planning/__init__.py

from fastapi import APIRouter

from .month_plan_assignee_web import (
    router as month_plan_assignee_web_router,
)
from .month_plan_web import router as month_plan_web_router
from .school_web import router as school_web_router
from .superuser_web import router as superuser_web_router
from .archive_web import router as archive_web_router


from .content_language_web import legacy_router as legacy_content_router

router = APIRouter()
router.include_router(legacy_content_router)

router.include_router(superuser_web_router)
router.include_router(school_web_router)
router.include_router(month_plan_web_router)
router.include_router(month_plan_assignee_web_router)
router.include_router(archive_web_router)

from .content_language_web import router as content_language_router
router.include_router(content_language_router)
