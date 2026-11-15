"""Request-local reverse URL index used only during synchronous template rendering.

No final URLs, users, hosts, or path parameters are cached across requests.
Incoming routing and authorization remain with the original router.
"""
from contextlib import contextmanager
from fastapi.routing import APIRoute, APIWebSocketRoute, APIRouter
from starlette.requests import HTTPConnection
from starlette.routing import Route, WebSocketRoute, Router, NoMatchFound

@contextmanager
def indexed_render_urls(request):
    scope = getattr(request, 'scope', None)
    router = scope.get('router') if isinstance(scope, dict) else None
    # Preserve custom request/router overrides, including nested invocations.
    if (not isinstance(request, HTTPConnection)
            or type(request).url_for is not HTTPConnection.url_for
            or 'url_for' in request.__dict__
            or type(router) not in (Router, APIRouter)
            or 'url_path_for' in router.__dict__):
        yield
        return

    by_name = {}
    general = []
    standard = (Route, WebSocketRoute, APIRoute, APIWebSocketRoute)
    for position, route in enumerate(router.routes):
        pair = (position, route)
        if type(route) in standard and 'url_path_for' not in route.__dict__:
            name = route.name
            if type(name) is str:
                by_name.setdefault(name, []).append(pair)
            else:
                general.append(pair)
        else:
            # Mount, Host and custom routes may resolve nested/dynamic names.
            # Keep their position and original method for every lookup.
            general.append(pair)

    original = request.url_for
    def url_for(name, /, **path_params):
        if type(name) is not str:
            return original(name, **path_params)
        named = by_name.get(name, ())
        # Both lists preserve route order; merging retains precedence of mounts
        # and duplicate names without scanning all ordinary unrelated routes.
        left = right = 0
        while left < len(named) or right < len(general):
            if right >= len(general) or (left < len(named) and named[left][0] < general[right][0]):
                route = named[left][1]
                left += 1
            else:
                route = general[right][1]
                right += 1
            try:
                path = route.url_path_for(name, **path_params)
            except NoMatchFound:
                continue
            return path.make_absolute_url(base_url=request.base_url)
        raise NoMatchFound(name, path_params)

    request.url_for = url_for
    try:
        yield
    finally:
        del request.url_for
