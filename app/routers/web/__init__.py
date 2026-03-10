# app/routers/web/__init__.py (Подключает все web-маршруты (HTML-страницы):)

from fastapi import APIRouter


from .core import router as core_router
from .auth import router as auth_router
from .setup import router as setup_router
from .dashboards import router as dashboards_router
from .codes import router as codes_router
from .reports import router as reports_router
from .org import router as org_router
from .planning import router as planning_router
from .staff import router as staff_router


router = APIRouter()
router.include_router(core_router)     # <-- ВАЖНО
router.include_router(auth_router)
router.include_router(setup_router)
router.include_router(dashboards_router)
router.include_router(codes_router)
router.include_router(reports_router)
router.include_router(org_router)
router.include_router(planning_router)
router.include_router(staff_router)
