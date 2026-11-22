"""Separate ASGI app: no School Monitor user authentication, menus or admin routes.
Development: uvicorn app.student_portal:app --host 127.0.0.1 --port 8001 --workers 1
"""
import secrets,time,hmac,asyncio,logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, Response
from app.modules.assessment.services import diagnostic_attempt_service as execution
from app.modules.assessment.helpers.diagnostic_presentation import image_keys
from app.modules.assessment.helpers.diagnostic_period import display as period_display
from collections import OrderedDict
from fastapi import FastAPI,Request
from fastapi.responses import HTMLResponse,RedirectResponse
from app.modules.assessment.repositories import diagnostic_attempt_repo as repository
import base64,json,hashlib
class BadSignature(ValueError): pass
class PortalSigner:
    def __init__(self,secret):self.key=hmac.digest(secret.encode(),b'separate-diagnostic-portal-v1','sha256')
    def dumps(self,value):
        raw=json.dumps([int(time.time()),value],separators=(',',':')).encode()
        body=base64.urlsafe_b64encode(raw).decode().rstrip('=')
        return body+'.'+hmac.new(self.key,body.encode(),hashlib.sha256).hexdigest()
    def loads(self,token,max_age):
        try:
            if not isinstance(token,str) or len(token)>4096:raise ValueError()
            body,signature=token.split('.')
            if not hmac.compare_digest(signature,hmac.new(self.key,body.encode(),hashlib.sha256).hexdigest()):raise ValueError()
            issued,value=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
            if type(issued) is not int or not -60<=time.time()-issued<=max_age or not isinstance(value,dict):raise ValueError()
            return value
        except (ValueError,TypeError,UnicodeError) as exc:raise BadSignature() from exc
from markupsafe import escape
from app.db.session import async_session_maker
from app.core.config import get_settings
from app.modules.assessment.services.diagnostic_session_service import digest
async def sweep_deadlines():
    while True:
        try:
            async with async_session_maker() as db:
                await execution.expire(db);await db.commit()
        except Exception:
            logging.getLogger(__name__).exception('Diagnostic deadline sweep failed')
        await asyncio.sleep(15)

@asynccontextmanager
async def lifespan(app):
    from app.core.feature_flags import assessment_enabled,get_features
    if get_features().RESTRICTED_MODULES_SUPERUSER_ONLY or not assessment_enabled():
        yield
        return
    worker=asyncio.create_task(sweep_deadlines())
    try:yield
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):await worker

app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
from app.core.feature_access import PortalFeatureGate
app.add_middleware(PortalFeatureGate)
root=Path(__file__).resolve().parent/'web'
app.mount('/assets',StaticFiles(directory=root/'static/student_portal'),name='pupil_assets')
views=Environment(loader=FileSystemLoader(root/'templates/student_portal'),autoescape=select_autoescape(['html']))
HEADERS={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','X-Content-Type-Options':'nosniff'}
MESSAGES={
    'access':('Вход недоступен. Введите код заново.','Кіру қолжетімсіз. Кодты қайта енгізіңіз.'),
    'subject':('Предмет не найден.','Пән табылмады.'),
    'finished':('Работа уже завершена.','Жұмыс аяқталды.'),
    'sequence':('Сначала завершите начатый предмет.','Алдымен басталған пәнді аяқтаңыз.'),
    'configuration':('Задание требует проверки организатором. Сообщите ему название предмета.','Тапсырманы ұйымдастырушы тексеруі қажет. Оған пәннің атауын хабарлаңыз.'),
    'format':('Проверьте ответы: в порядке шагов номера не должны повторяться.','Жауаптарды тексеріңіз: қадамдар ретіндегі нөмірлер қайталанбауы керек.'),
    'conflict':('Ответы изменены в другой вкладке.','Жауаптар басқа қойындыда өзгертілді.'),
    'not_open':('Период проведения ещё не начался.','Өткізу кезеңі әлі басталмады.'),
    'period_closed':('Период проведения завершён.','Өткізу кезеңі аяқталды.'),
    'insufficient':('До закрытия недостаточно времени для полного выполнения предмета.','Жабылғанға дейін пәнді толық орындауға уақыт жеткіліксіз.'),
    'csrf':('Сеанс страницы устарел.','Бет сеансы ескірді.'),
}

def identity(request):
    try:return signer.loads(request.cookies.get(COOKIE,''),max_age=43200)
    except BadSignature:raise execution.AttemptError('access',401) from None

def write_token(request):
    return hmac.new(signer.key,b'write:'+request.cookies.get(COOKIE,'').encode(),hashlib.sha256).hexdigest()

def check_write(request,value):
    if not isinstance(value,str) or not hmac.compare_digest(value,write_token(request)):
        raise execution.AttemptError('csrf',403)

@app.exception_handler(execution.AttemptError)
async def attempt_error(request,exc):
    message=' / '.join(MESSAGES[exc.code])
    if request.url.path.endswith('/save'):
        return JSONResponse(dict(message=message),status_code=exc.status,headers=HEADERS)
    if exc.code=='access':return RedirectResponse('/',303,headers=HEADERS)
    response=shell('<p>'+str(escape(message))+'</p><a href="/session">К предметам / Пәндерге</a>')
    response.status_code=exc.status;return response
signer=PortalSigner(get_settings().SECRET_KEY)
COOKIE='diagnostic_access';attempts=OrderedDict()
def shell(body):
    return HTMLResponse('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Диагностика / Диагностика</title><style>body{font:18px Arial;max-width:700px;margin:40px auto;padding:16px}input,button{font:inherit;padding:12px;margin:8px 0}button{background:#2563eb;color:white;border:0;border-radius:8px}li{margin:16px 0}.portal-code{display:block;box-sizing:border-box;width:100%;max-width:480px;min-width:0;border:1px solid #98a2b3;border-radius:8px;letter-spacing:.06em}.portal-code:focus{outline:3px solid #bfdbfe;outline-offset:2px;border-color:#2563eb}</style><main>'+body+'</main></html>',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','X-Content-Type-Options':'nosniff'})
@app.get('/')
async def entry(request:Request):
    token=signer.dumps(dict(csrf=secrets.token_urlsafe(24)))
    r=shell('<h1>Диагностика</h1><p>Введите индивидуальный код / Жеке кодты енгізіңіз</p><form method="post" action="/enter"><input type="hidden" name="csrf" value="'+token+'"><input class="portal-code" id="access-code" name="code" required maxlength="32" autocomplete="off" autocapitalize="characters" spellcheck="false" aria-label="Код / Код" placeholder="XXXX-XXXX-XXXX-XXXX"><button>Войти / Кіру</button></form>')
    r.set_cookie('diagnostic_csrf',token,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=1800);return r
@app.post('/enter')
async def enter(request:Request):
    form=await request.form();expected=request.cookies.get('diagnostic_csrf','')
    try:
        signer.loads(expected,max_age=1800)
        if not hmac.compare_digest(expected,str(form.get('csrf',''))):raise ValueError()
    except (BadSignature,ValueError):return shell('<p>Обновите страницу / Бетті жаңартыңыз</p><a href="/">Вход / Кіру</a>')
    ip=request.client.host if request.client else 'unknown';now=time.monotonic()
    times=[t for t in attempts.pop(ip,[]) if now-t<60];times.append(now);attempts[ip]=times
    while len(attempts)>10000:attempts.popitem(last=False)
    if len(times)>10:return shell('<p>Повторите через минуту / Бір минуттан кейін қайталаңыз</p>')
    async with async_session_maker() as db:
        person=await repository.login_person(db,digest(str(form.get('code',''))))
        if person is None:return shell('<p>Код недоступен / Код қолжетімсіз</p><a href="/">Вход / Кіру</a>')
        token=signer.dumps(dict(person=person.id,hash=person.access_hash))
    r=RedirectResponse('/session',303);r.set_cookie(COOKIE,token,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=43200);r.headers['Cache-Control']='no-store';return r
@app.get('/favicon.ico')
async def favicon():return Response(status_code=204)

@app.get('/session')
async def session_page(request:Request):
    async with async_session_maker() as db:
        person=await execution.authorize(db,identity(request),True)
        subjects=await execution.subject_list(db,person)
        session=await repository.session(db,person.session_id)
        calendar=('<p>Период / Кезең: '+period_display(session.opens_at)+' — '+period_display(session.closes_at)+' · UTC+5</p>') if session.opens_at else '<p>Период не задан / Кезең белгіленбеген</p>'
        body='<h1>'+str(escape(person.full_name))+'</h1><p>'+str(escape(person.class_label))+'</p>'+calendar+'<p>Между предметами можно делать перерывы. Начатый предмет выполняется без паузы.<br>Пәндер арасында үзіліс жасауға болады. Басталған пән үзіліссіз орындалады.</p><ul>'
        for subject in subjects:
            ru=subject['language']=='ru';state=subject['state'];sid=subject['id']
            body+='<li><b>'+str(escape(subject['name']))+'</b> · '+str(subject['minutes'])+' мин · '+('Вариант ' if ru else 'Нұсқа ')+str(subject['variant'])
            if state=='active':body+='<br><a href="/attempt/'+str(subject['attempt_id'])+'">'+('Продолжить' if ru else 'Жалғастыру')+'</a>'
            elif state=='ready':
                body+='<form method="post" action="/subject/'+str(sid)+'/start"><input type="hidden" name="csrf" value="'+write_token(request)+'"><p>'+('Нажатие запускает таймер этого предмета.' if ru else 'Басқан кезде осы пәннің таймері іске қосылады.')+'</p><button>'+('Начать' if ru else 'Бастау')+'</button></form>'
            else:body+='<p>'+({'not_open':MESSAGES['not_open'],'period_closed':MESSAGES['period_closed'],'insufficient':MESSAGES['insufficient'],'locked':('Сначала завершите начатый предмет.','Алдымен басталған пәнді аяқтаңыз.'),'submitted':('Оценивание завершено.','Бағалау аяқталды.'),'expired':('Время истекло. Сохранённые ответы приняты.','Уақыт аяқталды. Сақталған жауаптар қабылданды.')}[state][0 if ru else 1])+'</p>'
            if state in ('submitted','expired') and session.results_published_at:
                body+='<p><a href="/attempt/'+str(subject['attempt_id'])+'/result">'+('Результат и разбор ошибок' if ru else 'Нәтиже және қателерді талдау')+'</a></p>'
            elif state in ('submitted','expired'):
                body+='<p>'+('Результат появится после публикации организатором.' if ru else 'Нәтиже ұйымдастырушы жариялағаннан кейін көрсетіледі.')+'</p>'
            body+='</li>'
        await db.commit()
        return shell(body+'</ul>')

@app.post('/subject/{subject_id}/start')
async def subject_start(request:Request,subject_id:int):
    who=identity(request);form=await request.form();check_write(request,form.get('csrf'))
    async with async_session_maker() as db:
        aid=await execution.start(db,who,subject_id);await db.commit()
    return RedirectResponse('/attempt/'+str(aid),303,headers=HEADERS)

@app.get('/attempt/{attempt_id}')
async def attempt_page(request:Request,attempt_id:int):
    async with async_session_maker() as db:
        person,a=await execution.owned_attempt(db,identity(request),attempt_id,True)
        if a.status!='active':
            await db.commit();return RedirectResponse('/session',303,headers=HEADERS)
        from app.modules.assessment.helpers.assessment_names import subject_title
        subject=await repository.subject_info(db,a.diagnostic_subject_id)
        lang=person.assignments[str(subject.source_plan_id)]['language']
        session=await repository.session(db,person.session_id)
        body=views.get_template('work.html').render(language=lang,name=subject_title(subject,lang),
            pupil=person.full_name,attempt_id=a.id,version=a.version,csrf=write_token(request),
            seconds=max(0,(execution.utc(a.deadline_at)-await execution.now(db)).total_seconds()),
            questions=a.presentation,responses=a.responses,navigation=a.navigation or {},period_end=period_display(session.closes_at) if session.closes_at else None,tr=lambda ru,kk:ru if lang=='ru' else kk)
        await db.commit()
    return HTMLResponse(body,headers=HEADERS)

@app.post('/attempt/{attempt_id}/save')
async def attempt_save(request:Request,attempt_id:int):
    who=identity(request);check_write(request,request.headers.get('X-CSRF-Token'))
    content=bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content)>2_097_152:raise execution.AttemptError('format',413)
    try:body=json.loads(content)
    except (ValueError,UnicodeError):raise execution.AttemptError('format') from None
    async with async_session_maker() as db:
        result=await execution.save(db,who,attempt_id,body);await db.commit()
    return JSONResponse(result,headers=HEADERS)

@app.get('/attempt/{attempt_id}/image')
async def attempt_image(request:Request,attempt_id:int,object_key:str):
    async with async_session_maker() as db:
        _,a=await execution.owned_attempt(db,identity(request),attempt_id,True)
        if a.status!='active' or object_key not in image_keys(a.presentation):
            await db.commit();raise execution.AttemptError('subject',404)
        await db.commit()
    # Bounded storage read also works on a separate host with local storage.
    from app.core.storage import get_storage
    try:content=await get_storage().read(object_key=object_key,max_bytes=8_000_000)
    except (ValueError,OSError,FileNotFoundError):raise execution.AttemptError('subject',404) from None
    mime={'png':'image/png','jpg':'image/jpeg','webp':'image/webp'}[object_key.rsplit('.',1)[1]]
    return Response(content,media_type=mime,headers=HEADERS)


@app.get('/attempt/{attempt_id}/result')
async def result_page(request:Request,attempt_id:int):
    from app.modules.assessment.services.diagnostic_report_service import report
    async with async_session_maker() as db:
        context=await report(db,attempt_id,identity=identity(request))
        context.update(back_url='/session',image_url=f'/attempt/{attempt_id}/result/image')
        body=views.get_template('result.html').render(**context)
    return HTMLResponse(body,headers=HEADERS)


@app.get('/attempt/{attempt_id}/result/image')
async def result_image(request:Request,attempt_id:int,object_key:str):
    from app.modules.assessment.services.diagnostic_report_service import report
    async with async_session_maker() as db:
        context=await report(db,attempt_id,identity=identity(request))
        if object_key not in image_keys(context['attempt']['presentation']):raise execution.AttemptError('subject',404)
    from app.core.storage import get_storage
    try:content=await get_storage().read(object_key=object_key,max_bytes=8_000_000)
    except (ValueError,OSError,FileNotFoundError):raise execution.AttemptError('subject',404) from None
    mime={'png':'image/png','jpg':'image/jpeg','webp':'image/webp'}[object_key.rsplit('.',1)[1]]
    return Response(content,media_type=mime,headers=HEADERS)
