# app/modules/planning/routers/school_router.py
from fastapi import APIRouter

router = APIRouter(
    prefix="/planning/school",
    tags=["Planning.School.Web"],
)

