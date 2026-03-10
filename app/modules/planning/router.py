# app/modules/planning/router.py

from fastapi import APIRouter

from .routers import (
    superuser_router,
    school_router,
    school_api,

    archive_router,
)

router = APIRouter()

router.include_router(superuser_router)
router.include_router(school_router)
router.include_router(school_api)
#router.include_router(archive_router)
