from fastapi import APIRouter


from app.routers.web.monitoring.staff_rating_web import router as staff_rating_web_router


router = APIRouter()

router.include_router(staff_rating_web_router)
