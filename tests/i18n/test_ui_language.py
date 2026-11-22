import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import httpx
from fastapi import FastAPI
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.requests import Request
from starlette.datastructures import URLPath
from starlette.responses import HTMLResponse

from app.core.i18n import (catalog, normalize_language, resolve_language,
                           safe_return_url, translate)
from app.core.i18n_jinja import install_i18n

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT
spec = importlib.util.spec_from_file_location('ui_middleware', PROJECT/'app/middlewares/ui_language.py')
_middleware = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_middleware)
UILanguageMiddleware = _middleware.UILanguageMiddleware


def request(language='ru'):
    return Request({'type': 'http', 'method': 'GET', 'path': '/login',
                    'root_path': '', 'query_string': b'', 'scheme': 'http',
                    'router': SimpleNamespace(url_path_for=lambda name, **kwargs: URLPath('/'+name)),
                    'server': ('test', 80), 'headers': [(b'cookie', f'ui_language={language}'.encode())]})


def test_language_resolution():
    assert normalize_language('kz') == 'kk'
    assert normalize_language('KK-kz') == 'kk'
    assert normalize_language('en') is None
    req = request('kk')
    assert resolve_language(req) == 'kk'
    assert resolve_language(req, {'ui_language': 'ru'}) == 'ru'
    assert resolve_language(request('invalid')) == 'ru'
    req.state.ui_language = 'ru'
    assert resolve_language(req) == 'ru'


def test_return_urls():
    for value in ('https://evil.example', '//evil.example', '/%2fevil.example',
                  '/\\evil', '/%250aLocation:evil', '/ui/language', '\n//evil'):
        assert safe_return_url(value) == '/dashboards'
    assert safe_return_url('/teacher/question-bank?page=2&language=kz') == '/teacher/question-bank?page=2&language=kz'


def test_catalogs():
    assert translate('Войти', 'kk') == 'Кіру'
    assert translate('Войти', 'ru') == 'Войти'
    assert translate('<unknown>', 'kk') == '<unknown>'
    assert catalog('ru') is catalog('ru')


def environment():
    env = Environment(loader=FileSystemLoader(str(PROJECT/'app/web/templates')),
                      autoescape=select_autoescape(['html']))
    install_i18n(env)
    env.globals['MONTH_NAMES'] = {10: 'Қазан'}
    env.globals['url_for'] = lambda name, **kw: '/'+name
    return env


def test_all_localized_templates_and_escaping():
    env = environment()
    for locale in ('ru', 'kk'):
        for page in ('auth/login.html', 'dashboards/teacher.html', 'dashboards/question_bank_expert.html', 'dashboards/l0.html', 'dashboards/l1.html', 'dashboards/l2.html', 'dashboards/l3.html', 'dashboards/school_staff.html'):
            text = env.get_template(page).render(request=request(locale),
                user={'full_name': '<script>x</script>', 'role': 'teacher'},
                error='Неверный логин/ИИН или пароль', academic_year=SimpleNamespace(name='2026–2027'), today=SimpleNamespace(month=10))
            assert f'<html lang="{locale}">' in text
            assert '&lt;script&gt;x&lt;/script&gt;' in text
            assert '<script>x</script>' not in text
            assert ('Мұғалім панелі' if locale == 'kk' else 'Панель учителя') in text
    # Saved preference also works when callers bypass the shared render helper.
    text = env.get_template('auth/login.html').render(request=request('ru'),
        user={'ui_language': 'kk', 'role': 'teacher'}, error=None)
    assert '<html lang="kk">' in text


def test_parallel_requests_have_independent_languages():
    app = FastAPI()
    app.add_middleware(UILanguageMiddleware)
    env = environment()

    @app.get('/')
    async def page(req: Request):
        await asyncio.sleep(0)
        return HTMLResponse(env.from_string('{{ _("Войти") }}').render(request=req))

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            async def get(locale):
                result = await client.get('/', headers={'cookie': f'ui_language={locale}'})
                assert result.text == ('Кіру' if locale == 'kk' else 'Войти')
                assert result.headers['content-language'] == locale
                assert 'Cookie' in result.headers['vary']
            await asyncio.gather(*(get(x) for x in ['kk', 'ru']*20))
    asyncio.run(run())


def test_switch_route(monkeypatch):
    # Isolate UI behavior from the application's unrelated DB/model registry.
    db = SimpleNamespace(commits=0)
    user = SimpleNamespace(ui_language=None, is_active=True)
    async def commit(): db.commits += 1
    db.commit = commit
    async def get_db(): yield db
    async def get_by_id(session, user_id): return user if user_id == 7 else None
    stubs = {
        'app.db.session': {'get_db': get_db},
        'app.modules.users.deps': {'_get_session_user_id': lambda req: int(req.cookies.get('user_id', '0'))},
        'app.modules.users.repo': {'UserRepo': SimpleNamespace(get_by_id=get_by_id)},
    }
    for name, attrs in stubs.items():
        module=ModuleType(name);module.__dict__.update(attrs);monkeypatch.setitem(sys.modules,name,module)
    spec=importlib.util.spec_from_file_location('isolated_ui_language', PROJECT/'app/routers/web/ui_language.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    app=FastAPI();app.include_router(module.router)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            result=await client.post('/ui/language',data={'language':'kz','next':'/login'})
            assert result.status_code==303 and result.headers['location']=='/login'
            assert 'ui_language=kk' in result.headers['set-cookie']
            assert db.commits==0
            result=await client.post('/ui/language',data={'language':'kk','next':'//evil'},headers={'cookie':'user_id=7'})
            assert result.headers['location']=='/dashboards'
            assert user.ui_language=='kk' and db.commits==1
            result=await client.post('/ui/language',data={'language':'ru'},headers={'origin':'https://evil','cookie':'user_id=7'})
            assert result.status_code==403 and db.commits==1
            result=await client.post('/ui/language',data={'language':'en'})
            assert result.status_code==400
            user.is_active=False
            await client.post('/ui/language',data={'language':'ru'},headers={'cookie':'user_id=7'})
            assert db.commits==1
    asyncio.run(run())
