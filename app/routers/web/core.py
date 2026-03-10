# app/routers/web/core.py

from fastapi import APIRouter
from starlette.responses import RedirectResponse

router = APIRouter()


@router.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/login", status_code=303)
