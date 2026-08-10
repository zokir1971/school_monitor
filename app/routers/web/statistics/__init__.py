# app/routers/web/statistics/__init__.py

from fastapi import APIRouter
from app.routers.web.statistics.school_statistics_web import router as school_statistics_web


router = APIRouter()
router.include_router(school_statistics_web)
