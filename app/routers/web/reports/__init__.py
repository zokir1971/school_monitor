# app/routers/web/reports/__init__.py

from fastapi import APIRouter

from .execution_web import router as execution_web
from .task_reports_web import router as task_reports_web
from .user_template_web import router as user_template_web
from .lesson_observation_web import router as lesson_observation_web
from .checking_notebooks_web import router as checking_notebooks_web
from .report_verify_web import router as report_verify_web
from .staff_my_reports_web import router as staff_my_reports_web

router = APIRouter()

router.include_router(execution_web)
router.include_router(task_reports_web)
router.include_router(user_template_web)
router.include_router(lesson_observation_web)
router.include_router(checking_notebooks_web)
router.include_router(report_verify_web)
router.include_router(staff_my_reports_web)

from .assessment_reports_web import router as assessment_reports_web
router.include_router(assessment_reports_web)
