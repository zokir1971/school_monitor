"""Authorized server-side filters; response size never exceeds the selected page."""
from urllib.parse import urlencode
from app.modules.assessment.repositories import diagnostic_progress_repo as repo
from app.modules.assessment.repositories.diagnostic_selection_repo import optional_group
from app.modules.assessment.services.diagnostic_session_service import own
from app.modules.assessment.services.diagnostic_attempt_service import expire
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError,integer

STATUSES=('all','not_started','active','submitted','expired','pending_review','scored','error')


def optional_id(value):
    return None if value in (None,'','0',0) else integer(value,1,2147483647)


async def progress(db,user,session_id,*,category='all',page=1,values=None):
    session=await own(db,user,session_id)
    values=values or {}
    if category not in ('all','not_started','partial','completed'):raise WorkPlanError('Некорректный фильтр. / Сүзгі қате.')
    page=integer(page,1,1000000)
    page_size=integer(values.get('page_size',25),25,100)
    if page_size not in (25,50,100):raise WorkPlanError('Выберите 25, 50 или 100 строк. / 25, 50 немесе 100 жол таңдаңыз.')
    filters={key:optional_id(values.get(key)) for key in ('school_id','class_id','subject_id')}
    filters['district_id']=optional_group(values.get('district_id'))
    filters.update(q=str(values.get('q','')).strip(),status=values.get('status','all'))
    if len(filters['q'])>100 or filters['status'] not in STATUSES:raise WorkPlanError('Проверьте фильтры. / Сүзгілерді тексеріңіз.')
    districts,schools,classes=await repo.filter_options(db,session.id,filters['district_id'],filters['school_id'])
    if filters['district_id'] and filters['district_id'] not in {r['id'] for r in districts}:
        raise WorkPlanError('Район не входит в сессию. / Аудан сессияға кірмейді.')
    if filters['school_id'] and filters['school_id'] not in {r['school_id'] for r in schools}:
        raise WorkPlanError('Школа не входит в сессию. / Мектеп сессияға кірмейді.')
    if filters['class_id'] and filters['class_id'] not in {r['id'] for r in classes}:
        raise WorkPlanError('Выберите класс выбранной школы. / Таңдалған мектептің сыныбын таңдаңыз.')
    await expire(db,session_id=session.id)
    subjects,counts,total,page,rows,attempts,all_subjects=await repo.page_rows(db,session.id,category,page,filters=filters,page_size=page_size)
    if filters['subject_id'] and filters['subject_id'] not in {s.id for s in all_subjects}:
        raise WorkPlanError('Предмет не входит в сессию. / Пән сессияға кірмейді.')
    by_person={(a.participant_id,a.diagnostic_subject_id):a.status for a in attempts}
    people=[dict(id=r.id,full_name=r.full_name,school_name=r.school_name,class_label=r.class_label,
                 finished=r.finished,started=r.started,state=r.state,
                 subjects=[dict(state=by_person.get((r.id,s.id),'not_started'),**r.assignments.get(str(s.source_plan_id),{})) for s in subjects]) for r in rows]
    from app.modules.assessment.repositories import diagnostic_result_repo as results
    saved=await results.page_results(db,[p['id'] for p in people])
    result_counts=await results.publish_counts(db,session.id)
    for p in people:
        for subject,cell in zip(subjects,p['subjects']):cell['result']=saved.get((p['id'],subject.id))
    params={key:value for key,value in dict(filters,category=category,page_size=page_size).items() if value not in (None,'')}
    def page_url(number):return '?'+urlencode(dict(params,page=number))+'#diagnostic-participants'
    return dict(result_counts=result_counts,session=session,subjects=subjects,people=people,counts=counts,total=total,
        page=page,category=category,pages=max(1,(total+page_size-1)//page_size),all_count=sum(counts.values()),
        subject_count=len(all_subjects),subject_options=all_subjects,districts=districts,schools=schools,classes=classes,filters=filters,
        page_size=page_size,page_url=page_url,start_row=(page-1)*page_size+1 if total else 0,end_row=min(page*page_size,total))


async def filter_choices(db,user,session_id,values):
    session=await own(db,user,session_id)
    district_id=optional_group(values.get('district_id'));school_id=optional_id(values.get('school_id'))
    districts,schools,classes=await repo.filter_options(db,session.id,district_id,school_id)
    if district_id and district_id not in {r['id'] for r in districts}:raise WorkPlanError('Район не входит в сессию. / Аудан сессияға кірмейді.')
    if school_id and school_id not in {r['school_id'] for r in schools}:raise WorkPlanError('Школа не входит в выбранный район и сессию. / Мектеп таңдалған аудан мен сессияға кірмейді.')
    return dict(schools=[dict(id=r['school_id'],name=((r['district_name']+' · ') if not district_id and session.scope_kind=='region' else '')+r['name']) for r in schools],classes=[dict(id=r['id'],name=r['name']) for r in classes])
