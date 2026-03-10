# app/routers/web/auth/__init__.py

from fastapi import APIRouter

from .login import router as login_router
from .logout import router as logout_router
from .register_admin_by_code import router as register_router
from .register_staff_schools import router as register_staff_router

router = APIRouter()
router.include_router(login_router)
router.include_router(logout_router)
router.include_router(register_router)
router.include_router(register_staff_router)
