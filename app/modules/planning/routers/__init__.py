# app/modules/planning/routers/__init__.py
from .superuser_router import router as superuser_router
from .school_router import router as school_router
from .school_api import router as school_api
#from .archive_router import router as archive_router

__all__ = [
    "superuser_router",
    "school_router",
    "school_api",
    "archive_router",
]
