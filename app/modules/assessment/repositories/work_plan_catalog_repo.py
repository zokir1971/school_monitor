"""Owner/scoped, paged plan list. Usage is checked in SQL, never per row."""
from sqlalchemy import select,func,case,and_,or_,exists
from app.modules.assessment.models_work_plans import AssessmentWorkPlan as Plan
from app.modules.assessment.models_work_assignments import AssessmentWorkAssignment as Assignment
from app.modules.assessment.models_diagnostic_sessions import DiagnosticSubject
from app.modules.assessment.repositories import work_plan_repo as repo
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError,integer


def filters_from(values):
    result={'q':str(values.get('q','')).strip()[:120],'tab':str(values.get('tab','all'))}
    if result['tab'] not in ('all','draft','prepared','used'):raise WorkPlanError('Некорректный фильтр комплектов. / Жинақтар сүзгісі қате.')
    for key,low,high in (('subject_id',1,2147483647),('participant_grade',1,11),('quarter',1,4)):
        raw=values.get(key);result[key]=integer(raw,low,high) if raw not in (None,'') else None
    result['work_type']=str(values.get('work_type',''))
    if result['work_type'] not in ('','baseline','sor','soch'):raise WorkPlanError('Некорректный тип оценивания. / Бағалау түрі қате.')
    for key,allowed in (
        ('education_track',('','general','emn','ogn')),
        ('language_policy',('','auto','both','kk','ru')),
        ('input_mode',('','manual','online')),
        ('sort',('updated','created','title','id_desc')),
    ):
        result[key]=str(values.get(key,'updated' if key=='sort' else ''))
        if result[key] not in allowed:raise WorkPlanError('Некорректный фильтр комплектов. / Жинақтар сүзгісі қате.')
    return result


def used_clause():
    return or_(exists(select(Assignment.id).where(Assignment.work_plan_id==Plan.id)),
               exists(select(DiagnosticSubject.id).where(DiagnosticSubject.source_plan_id==Plan.id)))


async def browse(db,user,values,language='ru'):
    filters=filters_from(values)
    scopes=await repo.scope_options(db,user)
    allowed=[and_(Plan.scope_kind==s['kind'],getattr(Plan,s['kind']+'_id')==s['id']) for s in scopes]
    used=used_clause()
    category=case((used,'used'),(Plan.status=='draft','draft'),else_='prepared').label('category')
    clauses=[Plan.created_by_user_id==user.id,or_(*allowed) if allowed else Plan.id<0]
    if filters['q']:
        q=filters['q'];escaped=q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        text=or_(*(col.ilike('%'+escaped+'%',escape='\\') for col in (Plan.title,Plan.title_ru,Plan.title_kk)))
        clauses.append(or_(text,Plan.id==int(q)) if q.isascii() and q.isdecimal() and len(q)<11 and int(q)<=2147483647 else text)
    for key in ('subject_id','participant_grade','quarter','work_type','education_track','language_policy','input_mode'):
        if filters[key]:clauses.append(getattr(Plan,key)==filters[key])
    grouped=(await db.execute(select(category,func.count()).where(*clauses).group_by(category))).all()
    counts=dict(draft=0,prepared=0,used=0);counts.update({r[0]:r[1] for r in grouped});counts['all']=sum(counts.values())
    if filters['tab']!='all':clauses.append(category==filters['tab'])
    total=counts[filters['tab']];pages=max(1,(total+19)//20)
    page=min(integer(values.get('page',1),1,1000000),pages)
    title_column=Plan.title_kk if language=='kk' else Plan.title_ru
    orders={'updated':(Plan.updated_at.desc(),Plan.id.desc()),'created':(Plan.created_at.desc(),Plan.id.desc()),'title':(func.lower(func.coalesce(func.nullif(title_column,''),Plan.title)).asc(),Plan.id.asc()),'id_desc':(Plan.id.desc(),)}
    rows=(await db.execute(select(Plan,category).where(*clauses).order_by(*orders[filters['sort']]).offset((page-1)*20).limit(20))).all()
    return dict(plans=[r[0] for r in rows],plan_categories={r[0].id:r[1] for r in rows},filters=filters,
                counts=counts,total=total,page=page,pages=pages,scopes=scopes)
