# app/middlewares/auth.py

from starlette.types import ASGIApp, Scope, Receive, Send
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.db.session import async_session_maker
from app.modules.users.repo import UserRepo
from app.core.access_session import session_user_id, session_matches
from app.core.request_user239 import remember_verified_user, clear_verified_user

# Какие страницы считаем "вебом" и защищаем редиректом на /login
PUBLIC_PREFIXES = ("/static", "/login", "/setup")
PUBLIC_EXACT = ("/",)  # корень

PROTECTED_PREFIXES = ("/dashboard", "/dashboards", "/super", "/l1", "/l2", "/planning", "/access-recovery/manage", "/access-recovery/change-password")


class AuthRedirectMiddleware:
    """Verify each web request without an extra task group or body relay."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request = Request(scope, receive=receive, send=send)
        clear_verified_user(request)
        path = request.url.path

        # публичные пути
        if path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIXES):
            return await self.app(scope, receive, send)

        # защищённые web-страницы
        if path.startswith(PROTECTED_PREFIXES):
            uid = session_user_id(request)
            if not uid:
                resp = RedirectResponse(url="/login", status_code=302)
                resp.delete_cookie("user_id")
                return await resp(scope, receive, send)

            async with async_session_maker() as db:
                user = await UserRepo.get_by_id(db, uid)

            if not session_matches(request, user):
                request.session.clear()
                resp = RedirectResponse(url="/login", status_code=302)
                resp.delete_cookie("user_id")
                return await resp(scope, receive, send)

            remember_verified_user(request, user)

        try:
            return await self.app(scope, receive, send)
        finally:
            clear_verified_user(request)
