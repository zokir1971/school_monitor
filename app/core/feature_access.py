"""Feature gates complement existing authorization; disabled routes perform no operation."""
from urllib.parse import urlsplit
from fastapi import Depends,Request
from fastapi.responses import HTMLResponse,JSONResponse
from jinja2 import pass_context
from app.core.feature_flags import assessment_enabled,school_education_enabled,report_enabled

class FeatureUnavailable(Exception):
    def __init__(self,feature='assessment',user=None):self.feature=feature;self.user=user

def ensure_assessment():
    if not assessment_enabled():raise FeatureUnavailable()

def ensure_report(code):
    if not report_enabled(code):raise FeatureUnavailable()

def require_assessment_enabled():ensure_assessment()
require_assessment_enabled.feature_key='assessment'

def report_dependency(code):
    def check():ensure_report(code)
    if code=='knowledge_quality_table':check.feature_key='assessment'
    return check

# Import authorization lazily at module integration sites to avoid config/import cycles.
def education_dependency(current_user):
    async def check(user=Depends(current_user)):
        if not school_education_enabled(user):raise FeatureUnavailable('school_education',user)
    check.feature_key='school_education'
    return check

async def unavailable_response(request:Request,exc:FeatureUnavailable):
    from app.core.i18n import resolve_language
    language=resolve_language(request,exc.user)
    if language not in ('ru','kk'):language='ru'
    ru=language=='ru'
    title='Раздел временно недоступен' if ru else 'Бөлім уақытша қолжетімсіз'
    message=('Оценивание, качество знаний и аналитика временно отключены.' if ru else 'Бағалау, білім сапасы және талдау уақытша өшірілген.') if exc.feature=='assessment' else ('Учебный модуль временно отключён для школьного уровня.' if ru else 'Оқу модулі мектеп деңгейі үшін уақытша өшірілген.')
    headers={'Cache-Control':'no-store','Content-Language':language,'Vary':'Cookie, Accept'}
    if 'text/html' not in request.headers.get('accept',''):
        return JSONResponse({'detail':message,'code':'feature_disabled','feature':exc.feature},503,headers=headers)
    back='К панели' if ru else 'Панельге'
    # Standalone, no user lookup or external assets required, including pupil portal.
    html=f'''<!doctype html><html lang="{language}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>body{{margin:0;background:#f4f7fc;font:16px/1.6 Arial,sans-serif;color:#183052}}main{{max-width:680px;margin:10vh auto;padding:28px;background:white;border:1px solid #d8e2f0;border-radius:16px}}a{{display:inline-flex;align-items:center;min-height:40px;box-sizing:border-box;padding:8px 16px;background:#2856f6;color:white;border-radius:8px;text-decoration:none;white-space:nowrap}}@media(max-width:740px){{main{{margin:24px 14px}}}}</style><main><strong>School Monitor</strong><h1>{title}</h1><p>{message}</p><a href="/dashboards">{back}</a></main></html>'''
    return HTMLResponse(html,503,headers=headers)

class PortalFeatureGate:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']=='http' and not assessment_enabled():
            response=await unavailable_response(Request(scope),FeatureUnavailable())
            await response(scope,receive,send)
        else:await self.app(scope,receive,send)

def _dependencies(dependant):
    for child in dependant.dependencies:
        key=getattr(child.call,'feature_key',None)
        if key:yield key
        yield from _dependencies(child)

def feature_link_available(request,href,user=None):
    if assessment_enabled() and school_education_enabled(user):return True
    path=urlsplit(str(href)).path
    rules=getattr(request.app.state,'feature_link_rules',None)
    if rules is None:
        rules=[]
        for route in request.app.routes:
            if hasattr(route,'dependant'):
                keys=set(_dependencies(route.dependant))
                if keys:rules.append((route.path_regex,keys))
        request.app.state.feature_link_rules=rules
    for pattern,keys in rules:
        if pattern.fullmatch(path):
            if 'assessment' in keys and not assessment_enabled():return False
            if 'school_education' in keys and not school_education_enabled(user):return False
    return True

def install_feature_helpers(environment):
    @pass_context
    def link_available(context,href,user=None):return feature_link_available(context['request'],href,user or context.get('user'))
    environment.globals.update(assessment_enabled=assessment_enabled,school_education_enabled=school_education_enabled,
                               feature_report_available=report_enabled,feature_link_available=link_available)
