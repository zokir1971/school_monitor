# app/routers/web/setup/__init__.py
from fastapi import APIRouter

from .superuser import router as superuser_router

router = APIRouter()
router.include_router(superuser_router)

