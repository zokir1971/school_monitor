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
from .tasks import router as tasks_router
from .schools import router as schools_router
from .reviews import router as reviews_router
from .statistics import router as statistics_router
from .monitoring import router as monitoring_router
from .assessment import router as assessment_router
from .education import router as education_router


from .internal_notifications_web import router as internal_notifications_router

router = APIRouter()
router.include_router(internal_notifications_router)
router.include_router(core_router)
router.include_router(auth_router)
router.include_router(setup_router)
router.include_router(dashboards_router)
router.include_router(codes_router)
router.include_router(reports_router)
router.include_router(org_router)
router.include_router(planning_router)
router.include_router(staff_router)
router.include_router(tasks_router)
router.include_router(schools_router)
router.include_router(reviews_router)
router.include_router(statistics_router)
router.include_router(monitoring_router)
router.include_router(assessment_router)
router.include_router(education_router)
