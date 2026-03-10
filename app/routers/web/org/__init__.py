from fastapi import APIRouter

from .org_web import router as org_wed_router
from .org_import import router as org_import_router

router = APIRouter()

router.include_router(org_wed_router)
router.include_router(org_import_router)