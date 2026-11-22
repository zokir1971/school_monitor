# app/routers/web/statistics/__init__.py

from fastapi import APIRouter
from app.routers.web.statistics.school_statistics_web import router as school_statistics_web


router = APIRouter()
router.include_router(school_statistics_web)

from app.routers.web.statistics.territorial_statistics_web import router as territorial_statistics_web
router.include_router(territorial_statistics_web)

from app.routers.web.statistics.activity_statistics_web import router as activity_statistics_web
router.include_router(activity_statistics_web)

from app.routers.web.statistics.statistics_excel_web import router as statistics_excel_web
router.include_router(statistics_excel_web)
