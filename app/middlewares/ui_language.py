from app.core.i18n import resolve_language
from app.core.ui_locale_context import ui_locale


class UILanguageMiddleware:
    """No process-wide locale or extra database lookup on ordinary requests."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from starlette.requests import Request
        request = Request(scope)
        request.state.ui_language = resolve_language(request)

        async def send_localized(message):
            if message["type"] == "http.response.start":
                from starlette.datastructures import MutableHeaders
                headers = MutableHeaders(scope=message)
                if "text/html" in headers.get("content-type", ""):
                    headers["Content-Language"] = resolve_language(request)
                    headers.add_vary_header("Cookie")
            await send(message)
        token=ui_locale.set(request.state.ui_language)
        try:
            await self.app(scope, receive, send_localized)
        finally:
            ui_locale.reset(token)
