# app/routers/web/reviews/__init__.py

from fastapi import APIRouter
from app.routers.web.reviews.task_review_web import router as task_review_web_router
from app.routers.web.reviews.review_result_web import router as review_result_web_router

router = APIRouter()
router.include_router(task_review_web_router)
router.include_router(review_result_web_router)
