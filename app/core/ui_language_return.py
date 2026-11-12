"""Resolve a language switch to an internal GET page, without executing endpoints."""
from urllib.parse import unquote,urlsplit
from collections import OrderedDict
from starlette.routing import Match,NoMatchFound
from app.core.i18n import safe_return_url

# These actions can render a page on POST; language navigation must use its reader.
READERS = {
    '/education/class-subjects/update': 'school_class_subjects_page',
    '/planning/super/education/curriculum/save': 'super_curriculum_page',
}


def supports_get(request,target):
    # Per-router bounded cache of route compatibility only; no HTML or user data.
    router=request.app.router
    count=len(router.routes)
    state=getattr(router,'_language_get_cache',None)
    if state is None or state[0]!=count:
        state=(count,OrderedDict())
        router._language_get_cache=state
    cache=state[1]
    path=unquote(urlsplit(target).path)
    root=request.scope.get('root_path','')
    host=request.headers.get('host','')
    key=(root,path,host)
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    scope=dict(request.scope,method='GET',path=path,raw_path=path.encode('utf-8'),query_string=b'')
    result=any(route.matches(scope)[0]==Match.FULL for route in router.routes)
    cache[key]=result
    if len(cache)>1024:cache.popitem(last=False)
    return result


def language_read_url(request,value):
    """Apply existing URL safety checks, then check the actual GET route table."""
    target=safe_return_url(value)
    if supports_get(request,target):return target
    parts=urlsplit(target)
    path=unquote(parts.path)
    root=request.scope.get('root_path','')
    if root and path.startswith(root+'/'):path=path[len(root):]
    route_name=READERS.get(path.rstrip('/'))
    if route_name:
        try:
            path=request.url_for(route_name).path
            target=path+('?' + parts.query if parts.query else '')
            if supports_get(request,target):return target
        except NoMatchFound:
            pass
    return '/dashboards'
