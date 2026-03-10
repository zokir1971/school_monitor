# app/routers/web/staff/__init__.py

from fastapi import APIRouter
from .school_staff_web import router as school_staff_router
from .task_web import router as task_web_router

router = APIRouter()
router.include_router(school_staff_router)
router.include_router(task_web_router)
