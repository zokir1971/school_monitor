"""Authenticated reusable work builder; no school assignment or online launch here."""
import secrets,json,hashlib
from urllib.parse import urlencode,parse_qsl
from types import SimpleNamespace
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from app.db.session import get_db
from app.core.i18n import translate, resolve_language
from app.modules.assessment.helpers.bank_access import require_bank_reader
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError,integer
from app.modules.assessment.repositories import work_plan_repo as repo
from app.modules.assessment.repositories import work_plan_catalog_repo as catalog
from app.modules.assessment.services import work_plan_service as service
from app.modules.assessment.services import work_plan_builder_service as builder
from app.modules.assessment.services import work_plan_position_service as positions_service
from app.modules.assessment.services import work_plan_redistribution_service as redistribution
from app.modules.assessment.services import work_plan_deletion_service as deletion
from app.modules.assessment.helpers.work_plan_positions import position_rows,composition_revision
from app.modules.assessment.enums import AssessmentQuestionType,AssessmentQuestionDifficulty
from app.modules.assessment.services.bilingual_question_views import localized_view
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router=APIRouter(prefix='/assessment/work-plans',tags=['assessment-work-plans'])
COOKIE='assessment_work_plan_csrf'
LABELS=dict(baseline='Нулевой контроль',sor='СОР',soch='СОЧ',manual='Бумажное',online='Онлайн',
    school='Школа',district='Район',region='Регион',auto='По языку обучения',both='Оба языка',
    kk='Казахский',ru='Русский',draft='Черновик',prepared='Комплект подготовлен')

def response(request,template,context,status_code=200):
    token=request.cookies.get(COOKIE) or secrets.token_urlsafe(32)
    from app.modules.assessment.helpers.work_plan_presentation import title_for
    language=resolve_language(request,context.get('user'))
    for plan in ([context['plan']] if context.get('plan') else context.get('plans',[])):
        plan.display_title=title_for(plan,language)
    context.update(csrf_token=token,labels=LABELS)
    result=render(templates,request,template,context,status_code=status_code)
    result.set_cookie(COOKIE,token,httponly=True,samesite='strict',secure=request.url.scheme=='https')
    result.headers['Cache-Control']='no-store'
    return result

def csrf(request,form):
    expected=request.cookies.get(COOKIE,'');actual=str(form.get('csrf_token',''))
    if not expected or not secrets.compare_digest(expected,actual):
        raise HTTPException(403,translate('Обновите страницу и повторите действие.',resolve_language(request)))

def cursor(request,name='offset'):
    try: return integer(request.query_params.get(name,0),0,1_000_000)
    except WorkPlanError as exc: raise HTTPException(400,translate(str(exc),resolve_language(request))) from exc

async def home_context(db,user,values=None,error=None,after=0):
    rows=await repo.list_owned(db,user.id,after)
    subjects=await repo.subjects(db)
    return dict(user=user,values=values or {},error=error,subjects=subjects,subjects_by_id={s.id:s for s in subjects},
        scopes=await repo.scope_options(db,user),plans=rows[:20],after=after,
        next_after=rows[19].id if len(rows)>20 else None)

async def render_index(request,db,user,values=None,error=None,status_code=200):
    context=await catalog.browse(db,user,request.query_params if values is None else values,language=resolve_language(request,user))
    subjects=await repo.subjects(db)
    params={k:v for k,v in dict(context['filters'],page=context['page']).items() if v not in (None,'')}
    def list_url(**changes):
        return str(request.url_for('assessment_work_plan_index'))+'?'+urlencode(dict(params,**changes))
    context.update(user=user,subjects=subjects,subjects_by_id={s.id:s for s in subjects},list_url=list_url,
                   return_query=urlencode(params),error=error,deleted=request.query_params.get('deleted')=='1')
    return response(request,'assessment/work_plans/index.html',context,status_code)


def return_filters(raw):
    values=dict(parse_qsl(str(raw or '')[:2000],max_num_fields=30))
    filters=catalog.filters_from(values)
    filters['page']=integer(values.get('page',1),1,1000000)
    return {k:v for k,v in filters.items() if v not in (None,'')}


@router.get('',name='assessment_work_plan_index')
async def index(request:Request,db=Depends(get_db),user=Depends(require_bank_reader)):
    try:return await render_index(request,db,user)
    except WorkPlanError as exc:raise HTTPException(400,translate(str(exc),resolve_language(request,user))) from exc


@router.get('/{plan_id}/draft/remove',name='assessment_work_plan_delete_preview')
async def delete_preview(request:Request,plan_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    try:
        values=return_filters(request.query_params.get('return_query'))
        context=await deletion.review(db,user,plan_id)
        context.update(user=user,return_query=urlencode(values),list_url=str(request.url_for('assessment_work_plan_index'))+'?'+urlencode(values))
        return response(request,'assessment/work_plans/delete_draft.html',context)
    except (WorkPlanError,ValueError) as exc:raise HTTPException(400,translate(str(exc),resolve_language(request,user))) from exc


@router.post('/{plan_id}/draft/remove',name='assessment_work_plan_delete_confirm')
async def delete_confirm(request:Request,plan_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    form=await request.form();csrf(request,form)
    try:values=return_filters(form.get('return_query'))
    except (WorkPlanError,ValueError) as exc:raise HTTPException(400) from exc
    try:
        await deletion.remove(db,user,plan_id,str(form.get('revision','')))
        await db.commit()
    except WorkPlanError as exc:
        await db.rollback();await db.refresh(user)
        return await render_index(request,db,user,values,error=str(exc),status_code=409 if isinstance(exc,positions_service.CompositionChanged) else 400)
    except Exception:
        await db.rollback();raise
    target=str(request.url_for('assessment_work_plan_index'))+'?'+urlencode(dict(values,deleted='1'))
    return RedirectResponse(target,303)

@router.get('/new',name='assessment_work_plan_new')
async def new(request:Request,db=Depends(get_db),user=Depends(require_bank_reader)):
    # Only educational context is carried from the read-only bank; no mutations on GET.
    from datetime import datetime,timezone,timedelta
    today=datetime.now(timezone(timedelta(hours=5)))
    values={'academic_year_start':str(today.year if today.month>=9 else today.year-1)}
    try:
        raw=request.query_params
        if raw.get('subject_id'):values['subject_id']=str(integer(raw['subject_id'],1,2147483647))
        if raw.get('curriculum_grade'):
            values['participant_grade']=str(integer(raw['curriculum_grade'],1,11));values['work_type']='soch'
        if raw.get('quarter'):values['quarter']=str(integer(raw['quarter'],1,4))
        if raw.get('education_track') in ('general','emn','ogn'):values['education_track']=raw['education_track']
        return response(request,'assessment/work_plans/new.html',await home_context(db,user,values))
    except WorkPlanError as exc:raise HTTPException(400,translate(str(exc),resolve_language(request,user))) from exc

@router.post('',name='assessment_work_plan_create')
async def create(request:Request,db=Depends(get_db),user=Depends(require_bank_reader)):
    form=await request.form();csrf(request,form);values=dict(form)
    try:
        plan=await service.create(db,user,values);plan_id=plan.id;await db.commit()
    except WorkPlanError as exc:
        await db.rollback();await db.refresh(user)
        return response(request,'assessment/work_plans/new.html',await home_context(db,user,values,str(exc)),400)
    except Exception:
        await db.rollback();raise
    return RedirectResponse(request.url_for('assessment_work_plan_detail',plan_id=plan_id),303)

async def workspace(request,db,user,plan_id,error=None,status_code=200):
    try: plan=await service.own(db,user,plan_id)
    except WorkPlanError as exc: raise HTTPException(404,translate(str(exc),resolve_language(request,user))) from exc
    items=await repo.items(db,plan.id)
    assigned=await positions_service.is_used(db,plan.id)
    can_edit=plan.status=='draft' and not assigned
    legacy_bank=any(key in request.query_params for key in ('reference_id','objective_id','source_quarter','offset','after'))
    tab=request.query_params.get('tab','bank' if legacy_bank else 'composition')
    if tab not in ('composition','bank','delivery') or (tab=='bank' and not can_edit):tab='composition'
    bank_enabled=can_edit and tab=='bank'
    offset=cursor(request) if bank_enabled else 0
    selection=None
    source_quarter=None
    try:
        raw=request.query_params.get('objective_id') if bank_enabled else None
        objective_id=integer(raw,1,2_147_483_647) if raw else None
        source_quarter=service.source_quarter_value(plan,request.query_params.get('source_quarter')) if bank_enabled else None
        reference_id=request.query_params.get('reference_id')
        if bank_enabled and reference_id:
            goals,rows,selection=await service.alternatives(db,plan,reference_id,items,request.query_params.get('after',0))
            has_next=False
            await builder.annotate(db,plan,rows,items)
        else:
            goals,rows,has_next=await service.candidates(db,plan,offset,objective_id,source_quarter) if bank_enabled else ([],[],False)
            if bank_enabled: await builder.annotate(db,plan,rows,items)
    except WorkPlanError as exc:
        # Keep the builder usable if the reference was withdrawn or changed.
        error=str(exc);status_code=400;selection=None;objective_id=None;offset=0;source_quarter=None
        goals,rows,has_next=await service.candidates(db,plan) if bank_enabled else ([],[],False)
        if bank_enabled: await builder.annotate(db,plan,rows,items)
    subjects={s.id:s for s in await repo.subjects(db)}
    groups=service.grouped(plan,items)
    language=request.query_params.get('language')
    languages=service.required_languages(plan.language_policy)
    if language not in languages:
        interface=resolve_language(request,user);language=interface if interface in languages else languages[0]
    for group in groups:
        group['views']=[]
        for item in group['items']:
            view=localized_view(SimpleNamespace(question_type=AssessmentQuestionType(item.question_type),
                difficulty=AssessmentQuestionDifficulty(item.difficulty),max_score=item.max_score),item.payloads[language],language)
            view.bank_objectives=item.objectives
            group['views'].append((item,view))
    positions=position_rows(plan,items)
    matrix_views={row.id:view for group in groups for row,view in group['views']}
    for row in rows:
        anchor=getattr(getattr(row,'availability',None),'anchor',None)
        payload=anchor.payloads.get(language) if anchor else None
        row.display=localized_view(row.item,payload,language) if payload else row.item
    def matrix_media_url(name,**kwargs):
        if name=='teacher_question_bank_media_view':return request.url_for('assessment_work_plan_media',plan_id=plan.id)
        return request.url_for(name,**kwargs)
    suggested_variant=min(groups,key=lambda g:(len(g['items']),g['no']))['no']
    if selection:
        reference_row=next((i for i in items if i.bank_item_id==selection['reference'].id),None)
        suggested_variant=(reference_row.variant_no % plan.variant_count)+1 if reference_row else 2
    return response(request,'assessment/work_plans/workspace.html',dict(user=user,plan=plan,error=error,suggested_variant=suggested_variant,
        positions=positions,matrix_views=matrix_views,matrix_media_url=matrix_media_url,composition_revision=composition_revision(plan,items),
        tab=tab,can_edit=can_edit,has_items=bool(items),has_inferred=any(p['inferred'] for p in positions),
        has_common_pool=sum(p['common'] and not p['missing'] for p in positions)>=plan.variant_count,
        workspace_url=request.url_for('assessment_work_plan_detail',plan_id=plan.id).replace(query=request.url.query),
        subject=subjects.get(plan.subject_id),curriculum_subject=subjects.get(plan.curriculum_subject_id),
        scope_name=plan._scope_name,type_labels={v.value:v.label_kz for v in AssessmentQuestionType},difficulty_labels={v.value:v.label_kz for v in AssessmentQuestionDifficulty},groups=groups,rows=rows,selection=selection,source_quarter=source_quarter,goals=goals,objective_id=objective_id,offset=offset,has_next=has_next,
        used={i.bank_item_id for i in items},shared_ids={i.bank_item_id for i in items if i.is_shared},full_shared_ids={i.bank_item_id for i in items if sum(row.bank_item_id==i.bank_item_id for row in items)>=plan.variant_count},languages=languages,language=language,
        assigned=assigned,complete=not service.completeness(plan,items),builder_saved=bool(request.query_params.get('builder_saved')),
        selectable_saved=[seed for seed,slots in builder.existing_slots(plan,items).items() if len(slots)<plan.variant_count]),status_code)

@router.get('/{plan_id}',name='assessment_work_plan_detail')
async def detail(request:Request,plan_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    return await workspace(request,db,user,plan_id)

async def selection_page(request,db,user,plan_id,form,error=None,status_code=200):
    source_ids=builder.selected_ids(form.getlist('selection_ids') or form.getlist('item_ids'))
    selection_mode=str(form.get('selection_mode','variants'))
    plan,saved,families=await builder.preview(db,user,plan_id,source_ids,selection_mode)
    subjects={s.id:s for s in await repo.subjects(db)}
    languages=service.required_languages(plan.language_policy)
    language=str(form.get('language',''))
    if language not in languages:language=languages[0]
    raw_return=str(form.get('return_to',''))
    from app.core.i18n import safe_return_url
    fallback=str(request.url_for('assessment_work_plan_detail',plan_id=plan_id))
    return_to=safe_return_url(raw_return)
    if not return_to.startswith('/assessment/work-plans/'+str(plan_id)+'?') and return_to!='/assessment/work-plans/'+str(plan_id):return_to=fallback
    common_values=set(form.getlist('common_ids'))
    choice_previews={}
    for family in families:
        for candidate in [family.status.anchor,*family.choices]:
            choice_previews[candidate.source.id]=localized_view(candidate.source,candidate.payloads[language],language)
        for row in family.locked.values():
            choice_previews[row.bank_item_id]=localized_view(SimpleNamespace(question_type=AssessmentQuestionType(row.question_type),max_score=row.max_score),row.payloads[language],language)
        posted=form.get('distribution_version')=='pool_v1'
        family.values={v:form.get(f'v_{family.seed}_{v}',family.assignments[v]) if posted and v!=1 and v not in family.locked else family.assignments[v] for v in family.assignments}
        if error and posted:family.common=family.common_locked or (family.can_common and str(family.seed) in common_values)
        family.display=choice_previews[family.seed]
    totals={v:sum((r.max_score for r in saved if r.variant_no==v),start=0) for v in range(1,plan.variant_count+1)}
    after={v:total+sum((f.source.max_score for f in families if v not in f.locked),start=0) for v,total in totals.items()}
    revision=composition_revision(plan,saved)
    selection_context=hashlib.sha256(json.dumps([source_ids,selection_mode,revision]).encode()).hexdigest()
    return response(request,'assessment/work_plans/selection.html',dict(user=user,plan=plan,
        subject=subjects.get(plan.subject_id),families=families,error=error,source_ids=source_ids,selection_mode=selection_mode,
        totals=totals,after=after,selection_context=selection_context,distribution_revision=revision,selection_posted=bool(error),
        type_labels={v.value:v.label_kz for v in AssessmentQuestionType},difficulty_labels={v.value:v.label_kz for v in AssessmentQuestionDifficulty},
        languages=languages,language=language,return_to=return_to,choice_previews=choice_previews),status_code)

async def assignment_page(request,db,user,plan_id,error=None,status_code=200,confirmed=None):
    from datetime import datetime, timezone, timedelta
    from app.modules.assessment.repositories import work_plan_assignment_repo as assignments
    plan=await service.own(db,user,plan_id)
    now=datetime.now(timezone(timedelta(hours=5)))
    year=integer(request.query_params.get('year',now.year if now.month>=9 else now.year-1),2000,2100)
    after=cursor(request,'after');roster_after=cursor(request,'roster_after')
    classes=await assignments.classes(db,plan,year,after)
    people=await assignments.roster(db,plan.id,roster_after)
    return response(request,'assessment/work_plans/assignments.html',dict(user=user,plan=plan,error=error,
        year=year,classes=classes[:100],next_class=classes[99].id if len(classes)>100 else None,
        people=people[:100],next_person=people[99].id if len(people)>100 else None,confirmed=confirmed),status_code)

@router.get('/{plan_id}/participants',name='assessment_work_plan_participants')
async def participants(request:Request,plan_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    try:return await assignment_page(request,db,user,plan_id)
    except WorkPlanError as exc:raise HTTPException(404,translate(str(exc),resolve_language(request,user))) from exc

@router.post('/{plan_id}/participants',name='assessment_work_plan_assign')
async def assign_participants(request:Request,plan_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    from app.modules.assessment.services import work_plan_assignment_service as assignments
    form=await request.form();csrf(request,form)
    try:
        if form.get('confirm')=='1':
            await assignments.assign(db,user,plan_id,form.get('year'),form.getlist('class_ids'),str(form.get('roster_digest','')))
            await db.commit()
            return RedirectResponse(request.url_for('assessment_work_plan_participants',plan_id=plan_id),303)
        plan,year,ids,rows,skipped=await assignments.preview(db,user,plan_id,form.get('year'),form.getlist('class_ids'))
        from collections import Counter
        from app.modules.assessment.helpers.work_plan_rules import participant_language
        counts=Counter(participant_language(plan.language_policy,row.instruction_language) for row in rows)
        confirmed=dict(year=year,ids=ids,total=len(rows),skipped=skipped,counts=counts,digest=assignments.roster_digest(rows))
        return await assignment_page(request,db,user,plan_id,confirmed=confirmed)
    except WorkPlanError as exc:
        await db.rollback();await db.refresh(user)
        try:return await assignment_page(request,db,user,plan_id,error=str(exc),status_code=400)
        except WorkPlanError:raise HTTPException(404,translate(str(exc),resolve_language(request,user))) from exc
    except Exception:
        await db.rollback();raise

@router.get('/{plan_id}/preview/{audience}',name='assessment_work_plan_preview')
async def preview_document(request:Request,plan_id:int,audience:str,db=Depends(get_db),user=Depends(require_bank_reader)):
    from app.modules.assessment.helpers.work_plan_presentation import title_for,document_rows,adapt_print_rows
    from app.modules.assessment.repositories import work_plan_assignment_repo as assignments
    from decimal import Decimal
    try:
        plan=await service.own(db,user,plan_id)
        if audience not in ('teacher','student'):raise WorkPlanError('Выберите учительский или ученический просмотр.')
        person_id=request.query_params.get('participant_id')
        person=None
        if person_id:
            if audience!='student':raise WorkPlanError('Выберите учительский или ученический просмотр.')
            person=await assignments.participant(db,plan.id,integer(person_id,1,2147483647))
            if person is None:raise WorkPlanError('Участник не найден.')
        language=person.language if person else request.query_params.get('language',resolve_language(request,user))
        languages=service.required_languages(plan.language_policy)
        if language not in languages:
            if 'language' in request.query_params:raise WorkPlanError('Нет сохранённой версии на выбранном языке.')
            language=languages[0]
        variant=person.variant_no if person else integer(request.query_params.get('variant',1),1,plan.variant_count)
        items=[i for i in await repo.items(db,plan.id) if i.variant_no==variant]
        if not items:raise WorkPlanError('Добавьте задания в этот вариант.')
        response_mode=request.query_params.get('response_mode','choice')
        if response_mode not in ('choice','open'):raise WorkPlanError('Выберите учительский или ученический просмотр.')
        rows=adapt_print_rows(document_rows(items,language,audience),items,response_mode)
        subjects={s.id:s for s in await repo.subjects(db)}
        subject=subjects.get(plan.subject_id)
        subject_name=getattr(subject,'name_ru' if language=='ru' else 'name_kz',None) or '—'
        text=lambda message:translate(message,language)
        def doc_url(name,**kwargs):
            if name=='teacher_question_bank_media_view':return request.url_for('assessment_work_plan_media',plan_id=plan.id)
            return request.url_for(name,**kwargs)
        result=render(templates,request,'assessment/work_plans/document.html',dict(user=user,plan=plan,
            response_mode=response_mode,document_title=title_for(plan,language),subject_name=subject_name,language=language,variant=variant,
            languages=languages,audience=audience,rows=rows,person=person,total=sum((i.max_score for i in items),Decimal(0)),
            labels=LABELS,_=text,url_for=doc_url))
        if request.query_params.get('format')=='docx':
            from app.modules.assessment.services.work_plan_docx_service import export,ExportError
            from fastapi.responses import Response
            try: data=await export(result.body.decode('utf-8'),audience)
            except ExportError as exc:raise HTTPException(400,'DOCX: '+str(exc)) from exc
            result=Response(data,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                headers={'Content-Disposition':f'attachment; filename="work_{plan.id}_variant_{variant}_{language}_{audience}.docx"'})
        result.headers['Cache-Control']='no-store';result.headers['X-Robots-Tag']='noindex, noarchive'
        result.headers['Referrer-Policy']='same-origin'
        return result
    except WorkPlanError as exc:raise HTTPException(400,translate(str(exc),resolve_language(request,user))) from exc

@router.get('/{plan_id}/media/image',name='assessment_work_plan_media')
async def document_media(request:Request,plan_id:int,object_key:str,db=Depends(get_db),user=Depends(require_bank_reader)):
    # Only keys actually referenced by this owner's immutable snapshots are allowed.
    try:plan=await service.own(db,user,plan_id)
    except WorkPlanError as exc:raise HTTPException(404) from exc
    import re
    if not re.fullmatch(r'question-bank/media/[1-9][0-9]*/[0-9a-f]{32}\.(?:png|jpg|webp)',object_key):raise HTTPException(404)
    def keys(value):
        if isinstance(value,dict):
            if isinstance(value.get('object_key'),str):yield value['object_key']
            for child in value.values():yield from keys(child)
        elif isinstance(value,list):
            for child in value:yield from keys(child)
    if not any(object_key in set(keys(i.payloads)) for i in await repo.items(db,plan.id)):raise HTTPException(404)
    from app.core.storage.factory import get_storage
    storage=get_storage()
    if not await storage.exists(object_key=object_key):raise HTTPException(404)
    return RedirectResponse(await storage.get_download_url(object_key=object_key),307,headers={'Cache-Control':'no-store'})

@router.post('/{plan_id}/{action}',name='assessment_work_plan_action')
async def command(request:Request,plan_id:int,action:str,db=Depends(get_db),user=Depends(require_bank_reader)):
    form=await request.form();csrf(request,form)
    try:
        if action in ('titles','assemble','add','share','remove','prepare','reopen','delete'):
            locked=await service.own(db,user,plan_id,True)
            await positions_service.ensure_unused(db,locked)
        if action=='selection':
            return await selection_page(request,db,user,plan_id,form)
        if action=='titles':
            from app.modules.assessment.services.work_plan_assignment_service import has_assignments
            plan=await service.own(db,user,plan_id,True)
            if await has_assignments(db,plan.id):raise WorkPlanError('Комплект уже назначен участникам. Изменять его нельзя; создайте новый комплект.')
            await service.standardize_name(db,plan,dict(form))
        elif action=='assemble':
            if form.get('distribution_version')!='pool_v1':raise WorkPlanError('Форма обновлена. Проверьте новое распределение перед сохранением. / Нысан жаңартылды. Сақтау алдында жаңа бөлуді тексеріңіз.')
            seeds=builder.selected_ids(form.getlist('item_ids'))
            choices={(seed,v):form.get(f'v_{seed}_{v}') for seed in seeds for v in range(1,11)}
            await builder.assemble(db,user,plan_id,seeds,form.getlist('common_ids'),choices,expected_revision=str(form.get('distribution_revision','')))
        elif action=='add': await service.add(db,user,plan_id,form.get('variant_no'),form.getlist('item_ids'))
        elif action=='share': await service.set_shared(db,user,plan_id,integer(form.get('bank_item_id'),1,2_147_483_647),form.get('shared'))
        elif action=='remove': await service.remove(db,user,plan_id,integer(form.get('item_id'),1,2_147_483_647))
        elif action=='prepare': await service.prepare(db,user,plan_id)
        elif action=='reopen': await service.reopen(db,user,plan_id)
        elif action=='delete': await service.delete_draft(db,user,plan_id)
        else: raise HTTPException(404)
        await db.commit()
    except WorkPlanError as exc:
        await db.rollback();await db.refresh(user)
        if action=='assemble':
            try:return await selection_page(request,db,user,plan_id,form,error=str(exc),status_code=409 if isinstance(exc,positions_service.CompositionChanged) else 400)
            except WorkPlanError:pass
        return await workspace(request,db,user,plan_id,error=str(exc),status_code=409 if isinstance(exc,positions_service.CompositionChanged) else 400)
    except Exception:
        await db.rollback();raise
    if action=='delete': return RedirectResponse(request.url_for('assessment_work_plan_index'),303)
    target=request.url_for('assessment_work_plan_detail',plan_id=plan_id)
    if action=='assemble':target=target.include_query_params(builder_saved=secrets.token_urlsafe(12))
    language=str(form.get('language',''))
    if language in ('kk','ru'): target=target.include_query_params(language=language)
    return RedirectResponse(target,303)

@router.get('/{plan_id}/{action}',name='assessment_work_plan_command_return')
async def command_return(request:Request,plan_id:int,action:str,user=Depends(require_bank_reader)):
    # Language switching may return to a POST address: GET only redirects, never mutates.
    return RedirectResponse(request.url_for('assessment_work_plan_detail',plan_id=plan_id),303)


@router.get('/{plan_id}/positions/{item_id}/remove',name='assessment_work_plan_remove_position_preview')
async def remove_position_preview(request:Request,plan_id:int,item_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    try:
        plan,items,position,revision=await positions_service.reviewed_position(db,user,plan_id,item_id)
        languages=service.required_languages(plan.language_policy)
        language=request.query_params.get('language',resolve_language(request,user))
        if language not in languages:language=languages[0]
        rows=[]
        for v in range(1,plan.variant_count+1):
            row=position['slots'].get(v)
            total=sum((r.max_score for r in items if r.variant_no==v),start=0)
            rows.append(dict(variant=v,row=row,number=position['print_numbers'].get(v),
                title=row.payloads[language].get('title') if row else None,total=total,
                remaining=total-(row.max_score if row else 0)))
        return response(request,'assessment/work_plans/remove_position.html',dict(user=user,plan=plan,position=position,
            removals=rows,revision=revision,language=language,stale=bool(request.query_params.get('revision') and request.query_params['revision']!=revision)))
    except WorkPlanError as exc:raise HTTPException(400,translate(str(exc),resolve_language(request,user))) from exc


@router.post('/{plan_id}/positions/{item_id}/remove',name='assessment_work_plan_remove_position')
async def remove_position(request:Request,plan_id:int,item_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    form=await request.form();csrf(request,form)
    try:
        await positions_service.remove_position(db,user,plan_id,item_id,str(form.get('revision','')))
        await db.commit()
    except WorkPlanError as exc:
        await db.rollback();await db.refresh(user)
        return await workspace(request,db,user,plan_id,error=str(exc),status_code=409 if isinstance(exc,positions_service.CompositionChanged) else 400)
    except Exception:
        await db.rollback();raise
    language=str(form.get('language',''))
    target=request.url_for('assessment_work_plan_detail',plan_id=plan_id).include_query_params(tab='composition',position_removed='1')
    if language in ('kk','ru'):target=target.include_query_params(language=language)
    return RedirectResponse(target,303)

@router.get('/{plan_id}/redistribute/shared',name='assessment_work_plan_redistribute_preview')
async def redistribute_preview(request:Request,plan_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    try:
        data=await redistribution.proposal(db,user,plan_id)
        languages=service.required_languages(data['plan'].language_policy)
        language=request.query_params.get('language',resolve_language(request,user))
        if language not in languages:language=languages[0]
        data.update(user=user,language=language,error=None,checked_groups={g['key'] for g in data['groups']},
            type_labels={v.value:v.label_kz for v in AssessmentQuestionType},difficulty_labels={v.value:v.label_kz for v in AssessmentQuestionDifficulty})
        return response(request,'assessment/work_plans/redistribute_shared.html',data)
    except WorkPlanError as exc:raise HTTPException(400,translate(str(exc),resolve_language(request,user))) from exc


@router.post('/{plan_id}/redistribute/shared',name='assessment_work_plan_redistribute_apply')
async def redistribute_apply(request:Request,plan_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    form=await request.form();csrf(request,form)
    try:
        await redistribution.apply(db,user,plan_id,form.getlist('group_keys'),str(form.get('proposal_token','')))
        await db.commit()
    except WorkPlanError as exc:
        await db.rollback();await db.refresh(user)
        try:data=await redistribution.proposal(db,user,plan_id)
        except WorkPlanError:return await workspace(request,db,user,plan_id,error=str(exc),status_code=409 if isinstance(exc,positions_service.CompositionChanged) else 400)
        languages=service.required_languages(data['plan'].language_policy)
        language=str(form.get('language',''))
        if language not in languages:language=languages[0]
        allowed={g['key'] for g in data['groups']}
        checked=set() if isinstance(exc,positions_service.CompositionChanged) else set(form.getlist('group_keys'))&allowed
        data.update(user=user,language=language,error=str(exc),checked_groups=checked,
            type_labels={v.value:v.label_kz for v in AssessmentQuestionType},difficulty_labels={v.value:v.label_kz for v in AssessmentQuestionDifficulty})
        return response(request,'assessment/work_plans/redistribute_shared.html',data,409 if isinstance(exc,positions_service.CompositionChanged) else 400)
    except Exception:await db.rollback();raise
    language=str(form.get('language',''))
    target=request.url_for('assessment_work_plan_detail',plan_id=plan_id).include_query_params(tab='composition',redistributed='1')
    if language in ('kk','ru'):target=target.include_query_params(language=language)
    return RedirectResponse(target,303)
