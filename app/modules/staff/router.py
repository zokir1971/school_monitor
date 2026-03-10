# app/modules/staff/router.py
from fastapi import APIRouter
from app.modules.staff.staff_api import router as staff_api_router

router = APIRouter()
router.include_router(staff_api_router)
