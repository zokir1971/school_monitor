"""One durable job per logical session. A class and its cursor commit together."""
import csv,io,re,secrets,logging
from collections import Counter
from types import SimpleNamespace
from datetime import datetime,timezone
from sqlalchemy.exc import IntegrityError
from app.modules.assessment.models_diagnostic_preparation import DiagnosticPreparation as Job
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError,integer,participant_language
from app.modules.assessment.helpers.diagnostic_credentials import code,key_tag,check_key
from app.modules.assessment.helpers.diagnostic_period import utc,parse_period
from app.modules.assessment.repositories import diagnostic_preparation_repo as repo,work_plan_assignment_repo as roster
from app.modules.assessment.services import diagnostic_session_service as sessions
from app.modules.assessment.services import work_plan_service as works
logger=logging.getLogger(__name__)


async def enqueue(db,user,values,plan_ids,class_ids,secret):
    request_key=str(values.get('request_key',''))
    if not re.fullmatch('[a-f0-9]{32}',request_key):raise WorkPlanError('Обновите страницу создания сессии. / Сессия құру бетін жаңартыңыз.')
    # Serializes double clicks for this owner, including concurrent requests.
    await repo.lock_owner(db,user.id)
    previous=await repo.previous_job(db,user.id,request_key)
    if previous:
        await sessions.own(db,user,previous.session_id)
        return previous
    if values.get('select_filtered')=='1':
        context=await works.own(db,user,integer(values.get('context_plan_id'),1,2147483647))
        class_ids=await repo.filtered_ids(db,context,integer(values.get('year'),2000,2100),values)
    session,spec=await sessions.create(db,user,values,plan_ids,class_ids,prepare_only=True)
    spec['draft_key']=str(user.id)+':'+str(values.get('year'))+':'+str(values.get('context_plan_id'))
    nonce=secrets.token_hex(16)
    job=Job(session_id=session.id,owner_id=user.id,request_key=request_key,state='queued',spec=spec,nonce=nonce,key_tag=key_tag(secret,nonce),cursor=0,pupil_count=0)
    await repo.persist(db,job);return job


async def owner(db,job):
    user=await repo.user(db,job.owner_id)
    if user is None:raise WorkPlanError('Организатор недоступен. / Ұйымдастырушы қолжетімсіз.')
    # Match the ordinary bank-reader role policy, not just a surviving owner ID.
    role=getattr(user.role,'value',user.role)
    if role not in ('teacher','school_admin','school_staff','district_admin','district_staff','region_admin','region_staff','superuser'):
        raise WorkPlanError('Права организатора изменились. / Ұйымдастырушының құқықтары өзгерді.')
    if hasattr(user,'is_active') and not user.is_active:raise WorkPlanError('Организатор неактивен. / Ұйымдастырушы белсенді емес.')
    await sessions.own(db,user,job.session_id)
    return user


async def populate_class(db,session,job,secret):
    check_key(job,secret)
    await owner(db,job)
    spec=job.spec;context=SimpleNamespace(**spec['context'])
    if job.cursor>=len(spec['classes']):raise WorkPlanError('Некорректный курсор подготовки. / Дайындау көрсеткіші қате.')
    cls=spec['classes'][job.cursor]
    if await roster.selected_class_ids(db,context,session.academic_year_start,[cls],True)!={cls}:
        raise WorkPlanError(f'Класс №{cls} изменён или недоступен. / №{cls} сынып өзгерген немесе қолжетімсіз.')
    pupils=await roster.enrolled(db,context,session.academic_year_start,[cls],True,limit=5001)
    if len(pupils)>5000 or len({p.student_id for p in pupils})!=len(pupils):
        raise WorkPlanError(f'Проверьте численность и зачисления класса №{cls}. / №{cls} сыныптың саны мен қабылдауын тексеріңіз.')
    if job.pupil_count+len(pupils)>100000:raise WorkPlanError('Превышен лимит 100000 учеников. / 100000 оқушы шегінен асты.')
    configs={str(p['id']):p for p in spec['plans']}
    required={pid:set(p['languages']) for pid,p in configs.items()}
    counts=Counter();people=[]
    for pupil in pupils:
        if pupil.instruction_language not in ('kz','ru','uz','ug','tg'):
            raise WorkPlanError(f'Укажите язык обучения класса №{cls}. / №{cls} сыныптың оқу тілін көрсетіңіз.')
        assignments={}
        for pid,plan in configs.items():
            lang=participant_language(plan['language_policy'],pupil.instruction_language)
            if lang not in required[pid]:raise WorkPlanError(f'Нет нужной языковой версии для класса №{cls}. / №{cls} сынып үшін қажетті тіл нұсқасы жоқ.')
            low=min(counts[pid,v] for v in range(1,plan['variant_count']+1))
            variant=secrets.choice([v for v in range(1,plan['variant_count']+1) if counts[pid,v]==low]);counts[pid,variant]+=1
            assignments[pid]=dict(variant=variant,language=lang)
        people.append(dict(session_id=session.id,student_id=pupil.student_id,school_class_id=cls,
            full_name=' '.join(s for s in (pupil.last_name,pupil.first_name,pupil.middle_name) if s),
            class_label=f'{pupil.grade_level}{pupil.letter}',school_name=pupil.school_name,
            access_hash=sessions.digest(code(secret,job,pupil.student_id)),assignments=assignments))
    await repo.insert_people(db,people)
    job.pupil_count+=len(people);job.cursor+=1
    if job.cursor==len(spec['classes']):
        if not job.pupil_count:raise WorkPlanError('В выбранных классах нет учеников. / Таңдалған сыныптарда оқушылар жоқ.')
        from app.modules.assessment.services.diagnostic_attempt_service import now
        if session.closes_at and utc(session.closes_at)<=await now(db):
            raise WorkPlanError('Период закончился во время подготовки. Измените даты и продолжите. / Дайындау кезінде кезең аяқталды. Күндерді өзгертіп, жалғастырыңыз.')
        job.state='completed';session.status='prepared'
    else:job.state='running'
    job.error=None


async def process_one(db,secret):
    # Same lock order as organizer actions: Session -> Job. Locks survive the savepoint.
    session,job=await repo.claim(db)
    if session is None:return False
    if job.state not in ('queued','running'):return False
    try:
        async with db.begin_nested():await populate_class(db,session,job,secret)
    except Exception as exc:
        # Roll back the entire current class, retaining previously committed classes.
        await repo.refresh(db,job)
        job.state='failed'
        if isinstance(exc,WorkPlanError):job.error=str(exc)[:1000]
        elif isinstance(exc,IntegrityError):job.error='Повторное зачисление или изменение данных. Проверьте состав классов. / Қайталанған қабылдау немесе деректер өзгерісі. Сынып құрамын тексеріңіз.'
        else:
            job.error='Ошибка обработки. Проверьте журнал обработчика и повторите. / Өңдеу қатесі. Өңдегіш журналын тексеріп, қайталаңыз.'
            logger.error('Diagnostic preparation job %s failed: %s',job.id,type(exc).__name__)
    job.updated_at=datetime.now(timezone.utc)
    await repo.persist(db);return True


async def job_for(db,user,session_id,lock=False):
    session=await sessions.own(db,user,session_id,lock)
    job=await repo.job(db,session_id,lock)
    if job is None:raise WorkPlanError('Подготовка не найдена. / Дайындау табылмады.')
    return session,job


async def change(db,user,session_id,action,values):
    session,job=await job_for(db,user,session_id,True)
    if action=='retry' and job.state=='failed':
        from app.modules.assessment.services.diagnostic_attempt_service import now
        opening,closing=parse_period(values,await now(db));session.opens_at=opening;session.closes_at=closing
        job.state='queued';job.error=None
    elif action=='cancel' and job.state in ('queued','running','failed'):
        job.state='cancelled';session.status='closed'
    else:raise WorkPlanError('Действие недоступно. / Әрекет қолжетімсіз.')
    job.updated_at=datetime.now(timezone.utc);await repo.persist(db)


def csv_chunk(rows,job,secret,header=False):
    out=io.StringIO();writer=csv.writer(out,delimiter=';')
    if header:out.write('\ufeff');writer.writerow(['Школа / Мектеп','Класс / Сынып','ФИО / Аты-жөні','Код'])
    for row in rows:
        values=[row.school_name,row.class_label,row.full_name,code(secret,job,row.student_id)]
        writer.writerow(["'"+v if v.lstrip().startswith(('=','+','-','@')) else v for v in values])
    return out.getvalue().encode('utf-8')


async def code_stream(factory,job,secret):
    # Cursor paging: no 100k ORM objects, no transaction/connection held during network waits.
    check_key(job,secret)
    yield csv_chunk([],job,secret,True)
    after=0
    while True:
        async with factory() as db:
            rows=await repo.code_rows(db,job.session_id,after)
        if not rows:break
        yield csv_chunk(rows,job,secret);after=rows[-1].id
