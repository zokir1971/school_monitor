# app/routers/web/tasks/__init__.py

from fastapi import APIRouter
from .task_web import router as task_web_router

router = APIRouter()
router.include_router(task_web_router)
