# app/routers/web/schools/__init__.py

from fastapi import APIRouter
from .method_associations_web import router as method_associations_web_router

router = APIRouter()
router.include_router(method_associations_web_router)
