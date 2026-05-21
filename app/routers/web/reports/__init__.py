# app/routers/web/reports/__init__.py

from fastapi import APIRouter

from .school_report_web import router as school_report_web
from .template_report_web import router as template_report_web
from .user_template_web import router as user_template_web
from .checking_notebooks_router_web import router as checking_notebooks_web
from .system_report_web import router as system_report_web

router = APIRouter()

router.include_router(school_report_web)
router.include_router(template_report_web)
router.include_router(user_template_web)
router.include_router(checking_notebooks_web)
router.include_router(system_report_web)
