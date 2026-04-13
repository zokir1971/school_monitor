# app/routers/web/reports/__init__.py

from fastapi import APIRouter

from .school_report_web import router as school_report_web

router = APIRouter()

router.include_router(school_report_web)
