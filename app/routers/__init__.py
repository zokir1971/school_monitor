# app/routers/__init__.py (подключение всех маршрутов)

from fastapi import APIRouter
from app.routers.web import router as web_router
from app.modules.planning.router import router as planning_router
from app.modules.staff.router import router as staff_router
from app.modules.org.router import router as org_router

router = APIRouter()
router.include_router(web_router)
router.include_router(planning_router)
router.include_router(org_router)
router.include_router(staff_router)
