# app/modules/planning/routers/superuser_router.py

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/planning/super", tags=["planning.superuser"])
