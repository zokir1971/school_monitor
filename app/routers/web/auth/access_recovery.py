from urllib.parse import parse_qs,urlsplit
from datetime import timedelta,timezone
from fastapi import APIRouter,Depends,HTTPException,Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.modules.users.deps import get_current_user
from app.modules.users.services import access_recovery_service as service
from app.modules.users.repositories import access_recovery_repo as repo
from app.modules.users.recovery_policy import ADMIN_ROLES,role_value
from app.core.access_session import bind_session,csrf_matches,csrf_token
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router=APIRouter(prefix='/access-recovery',tags=['access-recovery'])
MESSAGES={
 'forbidden':('Нет прав на это действие.','Бұл әрекетке рұқсат жоқ.'),
 'invalid':('Данные или код неверны, код истёк либо уже использован. Обратитесь к своему администратору.','Деректер не код қате, кодтың мерзімі өткен немесе ол қолданылған. Өз әкімшіңізге хабарласыңыз.'),
 'rate':('Слишком много попыток. Подождите одну минуту.','Әрекет саны тым көп. Бір минут күтіңіз.'),
 'query':('Введите от 3 до 120 символов: логин, ФИО или полный ИИН.','3–120 таңба енгізіңіз: логин, аты-жөні немесе толық ЖСН.'),
 'not_found':('Пользователь недоступен в вашей области ответственности.','Пайдаланушы сіздің жауапкершілік ауқымыңызда қолжетімсіз.'),
 'inactive':('Учётная запись отключена. Сброс пароля не активирует её.','Тіркелгі өшірілген. Құпиясөзді қалпына келтіру оны белсендірмейді.'),
 'password_mismatch':('Новые пароли не совпадают.','Жаңа құпиясөздер сәйкес келмейді.'),
 'password_length':('Пароль должен содержать минимум 8 символов и не превышать 1024 байта.','Құпиясөз кемінде 8 таңбадан тұрып, 1024 байттан аспауы керек.'),
 'current_password':('Текущий пароль неверен.','Ағымдағы құпиясөз қате.'),
 'csrf':('Форма устарела. Обновите страницу и повторите ввод.','Нысан ескірген. Бетті жаңартып, деректерді қайта енгізіңіз.'),
 'bad_request':('Не удалось прочитать форму. Обновите страницу.','Нысанды оқу мүмкін болмады. Бетті жаңартыңыз.'),
}
ROLE_LABELS={
 'superuser':('Суперадминистратор','Бас әкімші'),'region_admin':('Администратор области','Облыс әкімшісі'),
 'district_admin':('Администратор района','Аудан әкімшісі'),'school_admin':('Администратор школы','Мектеп әкімшісі'),
 'region_staff':('Сотрудник области','Облыс қызметкері'),'district_staff':('Сотрудник района','Аудан қызметкері'),
 'school_staff':('Сотрудник школы','Мектеп қызметкері'),'teacher':('Учитель','Мұғалім'),
}


def language(request,user=None):
    # Recovery uses the same saved UI preference as the common header.
    from app.core.i18n import resolve_language
    return resolve_language(request,user)


def show(request,user=None,*,mode='recover',error=None,status_code=200,**context):
    lang=language(request,user);ru=lang=='ru'
    return_url='/access-recovery/manage' if mode in ('manage','issued') else '/access-recovery/change-password' if mode=='change' else '/access-recovery'
    response=render(templates,request,'auth/access_recovery.html',dict(user=user,mode=mode,language=lang,ru=ru,
        csrf=csrf_token(request),recovery_return_url=return_url,language_return_url=lambda:return_url,error=MESSAGES[error][0 if ru else 1] if error else None,
        role_labels={key:value[0 if ru else 1] for key,value in ROLE_LABELS.items()},
        display_time=lambda value:value.astimezone(timezone(timedelta(hours=5))).strftime('%d.%m.%Y %H:%M'),**context),status_code=status_code)
    response.headers['Cache-Control']='no-store, max-age=0'
    response.headers['Pragma']='no-cache';response.headers['Referrer-Policy']='same-origin'  # Same-site form POSTs must retain their real Origin.
    response.headers['X-Content-Type-Options']='nosniff'
    return response


async def checked_form(request):
    if request.headers.get('content-type','').split(';')[0].lower()!='application/x-www-form-urlencoded':raise service.RecoveryError('bad_request')
    chunks=[];size=0
    async for chunk in request.stream():
        size+=len(chunk)
        if size>16384:raise service.RecoveryError('bad_request')
        chunks.append(chunk)
    try:
        values=parse_qs(b''.join(chunks).decode('utf-8'),keep_blank_values=True,max_num_fields=12,errors='strict')
    except (ValueError,UnicodeError):raise service.RecoveryError('bad_request')
    if any(len(v)!=1 for v in values.values()):raise service.RecoveryError('bad_request')
    form={k:v[0] for k,v in values.items()}
    if not csrf_matches(request,form.get('csrf')):raise service.RecoveryError('csrf')
    origin=request.headers.get('origin')
    try:
        if origin and urlsplit(origin).netloc.lower()!=request.url.netloc.lower():raise service.RecoveryError('csrf')
    except ValueError:raise service.RecoveryError('csrf')
    return form


async def manager(user=Depends(get_current_user)):
    if role_value(user.role) not in ADMIN_ROLES:raise HTTPException(403,'Forbidden')
    return user


@router.get('',name='access_recovery_page')
async def recovery_page(request:Request):
    return show(request)


@router.post('',name='access_recovery_submit')
async def recovery_submit(request:Request,db:AsyncSession=Depends(get_db)):
    try:
        form=await checked_form(request)
        client=request.client.host if request.client else 'unknown'
        username=await service.redeem(db,form.get('identifier',''),form.get('code',''),form.get('password',''),form.get('confirmation',''),client)
        await db.commit();request.session.clear()
        response=show(request,done=True,username=username)
        response.delete_cookie('user_id')
        return response
    except service.RecoveryError as exc:
        await db.commit()  # Persist only throttling/audit for rejected attempts.
        return show(request,error=exc.code,status_code=429 if exc.code=='rate' else 400)
    except Exception:
        await db.rollback();raise


@router.get('/manage',name='access_recovery_manage')
async def manage(request:Request,db:AsyncSession=Depends(get_db),user=Depends(manager)):
    try:actor=await service.admin(db,user.id)
    except service.RecoveryError as exc:return show(request,user,mode='manage',rows=[],error=exc.code,status_code=403)
    return show(request,user,mode='manage',rows=[],history=await repo.history(db,actor))


@router.post('/manage/search',name='access_recovery_search')
async def search(request:Request,db:AsyncSession=Depends(get_db),user=Depends(manager)):
    try:
        form=await checked_form(request)
        rows,overflow=await service.search(db,user.id,form.get('query',''))
        await db.commit()
        return show(request,user,mode='manage',rows=rows,overflow=overflow,searched=True)
    except service.RecoveryError as exc:
        await db.commit()
        return show(request,user,mode='manage',rows=[],error=exc.code,status_code=429 if exc.code=='rate' else 400)
    except Exception:
        await db.rollback();raise


@router.post('/manage/issue',name='access_recovery_issue')
async def issue(request:Request,db:AsyncSession=Depends(get_db),user=Depends(manager)):
    try:
        form=await checked_form(request)
        raw=form.get('target_id','')
        if not raw.isdigit() or not 0<int(raw)<2147483648:raise service.RecoveryError('not_found')
        issued=await service.issue(db,user.id,int(raw))
        await db.commit()
        return show(request,user,mode='issued',issued=issued)
    except service.RecoveryError as exc:
        await db.commit()
        return show(request,user,mode='manage',rows=[],error=exc.code,status_code=429 if exc.code=='rate' else 400)
    except Exception:
        await db.rollback();raise


@router.get('/change-password',name='access_password_change')
async def change_page(request:Request,user=Depends(get_current_user)):
    return show(request,user,mode='change')


@router.post('/change-password',name='access_password_change_submit')
async def change_submit(request:Request,db:AsyncSession=Depends(get_db),user=Depends(get_current_user)):
    try:
        form=await checked_form(request)
        changed=await service.change_password(db,user.id,form.get('current_password',''),form.get('password',''),form.get('confirmation',''))
        await db.commit()
        from types import SimpleNamespace
        workspace=request.session.get('active_workspace')
        bind_session(request,SimpleNamespace(**changed))
        if isinstance(workspace,str):request.session['active_workspace']=workspace
        return show(request,user,mode='change',done=True)
    except service.RecoveryError as exc:
        await db.commit()
        return show(request,user,mode='change',error=exc.code,status_code=429 if exc.code=='rate' else 400)
    except Exception:
        await db.rollback();raise
