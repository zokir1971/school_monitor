# app/middlewares/auth.py

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.db.session import async_session_maker
from app.modules.users.services.user_service import UserCrudService

# Какие страницы считаем "вебом" и защищаем редиректом на /login
PUBLIC_PREFIXES = ("/static", "/login", "/setup")
PUBLIC_EXACT = ("/",)  # корень

PROTECTED_PREFIXES = ("/dashboard", "/dashboards", "/super", "/l1", "/l2", "/planning")


class AuthRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # публичные пути
        if path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)

        # защищённые web-страницы
        if path.startswith(PROTECTED_PREFIXES):
            user_id = request.cookies.get("user_id")
            if not user_id:
                return RedirectResponse(url="/login", status_code=302)

            try:
                uid = int(user_id)
            except ValueError:
                resp = RedirectResponse(url="/login", status_code=302)
                resp.delete_cookie("user_id")
                return resp

            async with async_session_maker() as db:
                user = await UserCrudService.get_by_id(db, uid)

            if not user or not user.is_active:
                resp = RedirectResponse(url="/login", status_code=302)
                resp.delete_cookie("user_id")
                return resp

        return await call_next(request)
