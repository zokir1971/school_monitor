# app/middlewares/auth.py

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.db.session import async_session_maker
from app.modules.users.repo import UserRepo
from app.core.access_session import session_user_id, session_matches

# Какие страницы считаем "вебом" и защищаем редиректом на /login
PUBLIC_PREFIXES = ("/static", "/login", "/setup")
PUBLIC_EXACT = ("/",)  # корень

PROTECTED_PREFIXES = ("/dashboard", "/dashboards", "/super", "/l1", "/l2", "/planning", "/access-recovery/manage", "/access-recovery/change-password")


class AuthRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # публичные пути
        if path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)

        # защищённые web-страницы
        if path.startswith(PROTECTED_PREFIXES):
            uid = session_user_id(request)
            if not uid:
                resp = RedirectResponse(url="/login", status_code=302)
                resp.delete_cookie("user_id")
                return resp

            async with async_session_maker() as db:
                user = await UserRepo.get_by_id(db, uid)

            if not session_matches(request, user):
                request.session.clear()
                resp = RedirectResponse(url="/login", status_code=302)
                resp.delete_cookie("user_id")
                return resp

        return await call_next(request)
