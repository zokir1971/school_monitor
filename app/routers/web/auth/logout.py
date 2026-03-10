# app/routers/web/auth/logout.py
from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from starlette import status

router = APIRouter()


# -----------------------
# Logout
# -----------------------
@router.post("/logout")
async def logout_action():
    resp = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    resp.delete_cookie("user_id")
    return resp
