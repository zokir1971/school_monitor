import csv,io,secrets
from urllib.parse import urlencode
from app.modules.assessment.repositories import diagnostic_selection_repo as picker
from datetime import datetime,timedelta,timezone
from app.modules.assessment.helpers.diagnostic_period import local_input,display
from app.modules.assessment.services import diagnostic_progress_service as tracking
from app.modules.assessment.repositories import diagnostic_session_repo as repository,diagnostic_preparation_repo as job_repo
from fastapi import APIRouter,Depends,Request,HTTPException
from fastapi.responses import Response,RedirectResponse,StreamingResponse
from app.db.session import get_db
from app.modules.assessment.helpers.bank_access import require_bank_reader
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError,integer
from app.modules.assessment.services import diagnostic_session_service as service,work_plan_service as works
from app.routers.web.assessment.work_plan_web import response,csrf
from app.modules.assessment.services import diagnostic_preparation_service as preparation
router=APIRouter(prefix='/assessment/diagnostics')
def codes(rows,session_id):
    output=io.StringIO();writer=csv.writer(output,delimiter=';');writer.writerow(['Школа / Мектеп','Класс / Сынып','ФИО / Аты-жөні','Код']);writer.writerows([[("'"+str(value)) if str(value).lstrip().startswith(('=','+','-','@')) else str(value) for value in row] for row in rows])
    return Response(('\ufeff'+output.getvalue()).encode('utf-8'),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="diagnostic_{session_id}_codes.csv"','Cache-Control':'no-store'})
async def page(request,db,user,error=None,values=None):
    values=values or {}
    plans=await repository.prepared_plans(db,user.id)
    year=integer(values.get('year',request.query_params.get('year',datetime.now().year)),2000,2100)
    chosen=values.get('context_plan_id',request.query_params.get('plan_id'))
    selection=dict(classes=[],regions={},districts={},schools={},class_total=0,class_page=1,class_pages=1,
                   filter_region_id=None,filter_district_id=None,filter_school_id=None,scope_kind=None)
    if chosen:
        first=await works.own(db,user,integer(chosen,1,2147483647))
        if first.status!='prepared':raise WorkPlanError('Сначала подготовьте комплект. / Алдымен жинақты дайындаңыз.')
        # A plan opened from search remains selectable even outside the latest 100.
        if not any(p.id==first.id for p in plans):plans.insert(0,first)
        filters={key:values.get(key,request.query_params.get(key,'')) for key in ('filter_region_id','filter_district_id','filter_school_id','class_page')}
        if not filters['class_page']:filters['class_page']='1'
        selection=await picker.selection(db,first,year,filters)
    sessions=await repository.recent(db,user.id)
    jobs=await repository.jobs(db,[s.id for s in sessions])
    query=dict(year=year,plan_id=chosen or '',**{k:selection[k] or '' for k in ('filter_region_id','filter_district_id','filter_school_id')})
    def class_url(page):return str(request.url_for('diagnostic_sessions'))+'?'+urlencode(dict(query,class_page=page))
    context=dict(user=user,jobs=jobs,request_key=values.get("request_key") or secrets.token_hex(16),plans=plans,year=year,chosen=chosen,sessions=sessions,error=error,values=values,
        selected_plans=set(values.getlist('plan_ids')) if hasattr(values,'getlist') else ({str(chosen)} if chosen else set()),
        selected_classes=set(values.getlist('class_ids')) if hasattr(values,'getlist') else set(),
        local_input=local_input,period_display=display,default_open=local_input(datetime.now(timezone.utc)),
        default_close=local_input(datetime.now(timezone.utc)+timedelta(days=7)),selection_posted=bool(values),
        previous_class_url=class_url(selection['class_page']-1),next_class_url=class_url(selection['class_page']+1),**selection)
    return response(request,'assessment/diagnostics/index.html',context,400 if error else 200)
@router.get('',name='diagnostic_sessions')
async def index(request:Request,db=Depends(get_db),user=Depends(require_bank_reader)):
    try:return await page(request,db,user)
    except WorkPlanError as exc:raise HTTPException(400,str(exc)) from exc
@router.post('',name='diagnostic_create')
async def create(request:Request,db=Depends(get_db),user=Depends(require_bank_reader)):
    form=await request.form(max_fields=5200);csrf(request,form)
    try:
        from app.core.config import get_settings
        job=await preparation.enqueue(db,user,dict(form),form.getlist('plan_ids'),form.getlist('class_ids'),get_settings().SECRET_KEY)
        session_id=job.session_id;await db.commit()
        return RedirectResponse(request.url_for('diagnostic_preparation',session_id=session_id),303)
    except WorkPlanError as exc:
        await db.rollback();await repository.refresh(db,user)
        try:return await page(request,db,user,str(exc),form)
        except WorkPlanError:raise HTTPException(400,str(exc)) from exc
    except Exception:await db.rollback();raise
@router.post('/{session_id}/period',name='diagnostic_period')
async def period(request:Request,session_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    form=await request.form();csrf(request,form)
    try:
        await service.update_period(db,user,session_id,dict(form));await db.commit()
        return RedirectResponse(request.url_for('diagnostic_sessions'),303)
    except WorkPlanError as exc:
        await db.rollback();await repository.refresh(db,user)
        return await page(request,db,user,str(exc))
    except Exception:await db.rollback();raise


@router.get('/{session_id}/preparation',name='diagnostic_preparation')
async def preparation_page(request:Request,session_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    try:
        session,job=await preparation.job_for(db,user,session_id)
        return response(request,'assessment/diagnostics/preparation.html',dict(user=user,session=session,job=job,period_display=display,local_input=local_input))
    except WorkPlanError as exc:raise HTTPException(400,str(exc)) from exc


@router.post('/{session_id}/preparation/{operation}',name='diagnostic_preparation_action')
async def preparation_action(request:Request,session_id:int,operation:str,db=Depends(get_db),user=Depends(require_bank_reader)):
    form=await request.form();csrf(request,form)
    try:
        await preparation.change(db,user,session_id,operation,dict(form));await db.commit()
        return RedirectResponse(request.url_for('diagnostic_preparation',session_id=session_id),303)
    except WorkPlanError as exc:
        await db.rollback();raise HTTPException(400,str(exc)) from exc
    except Exception:await db.rollback();raise


@router.get('/{session_id}/codes.csv',name='diagnostic_preparation_codes')
async def preparation_codes(request:Request,session_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    try:
        from app.core.config import get_settings
        from app.db.session import async_session_maker
        from app.modules.assessment.helpers.diagnostic_credentials import check_key
        session,job=await preparation.job_for(db,user,session_id)
        if job.state!='completed' or session.status!='prepared':raise WorkPlanError('Коды пока недоступны. / Кодтар әзірге қолжетімсіз.')
        secret=get_settings().SECRET_KEY;check_key(job,secret)
        # Detached plain descriptor, no live ORM transaction in the streaming iterator.
        from types import SimpleNamespace
        descriptor=SimpleNamespace(session_id=session.id,nonce=job.nonce,key_tag=job.key_tag)
        await db.commit()
        return StreamingResponse(preparation.code_stream(async_session_maker,descriptor,secret),media_type='text/csv',headers={
            'Content-Disposition':f'attachment; filename="diagnostic_{session_id}_codes.csv"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
    except WorkPlanError as exc:raise HTTPException(400,str(exc)) from exc


@router.post('/{session_id}/{action}',name='diagnostic_action')
async def action(request:Request,session_id:int,action:str,db=Depends(get_db),user=Depends(require_bank_reader)):
    form=await request.form();csrf(request,form)
    try:
        session=await service.own(db,user,session_id,True)
        job=await job_repo.job(db,session.id,True)
        if action=='close':
            session.status='closed'
            if job and job.state in ('queued','running','failed'):job.state='cancelled'
            await db.commit();return RedirectResponse(request.url_for('diagnostic_sessions'),303)
        if job:raise WorkPlanError('Используйте скачивание кодов на странице подготовки. / Дайындау бетіндегі кодтарды жүктеуді пайдаланыңыз.')
        if action!='codes' or session.status!='prepared':raise WorkPlanError('Действие недоступно.')
        people=await repository.locked_people(db,session.id)
        rows=[]
        for person in people:
            raw=service.access_code();person.access_hash=service.digest(raw)
            rows.append((person.school_name,person.class_label,person.full_name,'-'.join(raw[i:i+4] for i in range(0,16,4))))
        await db.commit();return codes(rows,session.id)
    except WorkPlanError as exc:await db.rollback();raise HTTPException(400,str(exc)) from exc
    except Exception:await db.rollback();raise


@router.get('/{session_id}/progress',name='diagnostic_progress')
async def progress(request:Request,session_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    try:
        context=await tracking.progress(db,user,session_id,category=request.query_params.get('category','all'),page=request.query_params.get('page','1'),values=request.query_params)
        from app.modules.assessment.services.diagnostic_analytics_service import overview
        context['analytics_subjects']=await overview(db,session_id)
        context.update(user=user,period_display=display)
        result=response(request,'assessment/diagnostics/progress.html',context)
        await db.commit();return result
    except WorkPlanError as exc:
        await db.rollback();raise HTTPException(400,str(exc)) from exc
    except Exception:await db.rollback();raise


@router.post('/{session_id}/results/publish',name='diagnostic_results_publish')
async def publish_results(request:Request,session_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    from app.modules.assessment.services.diagnostic_result_service import publish
    form=await request.form();csrf(request,form)
    try:
        await publish(db,user,session_id);await db.commit()
        return RedirectResponse(request.url_for('diagnostic_progress',session_id=session_id),303)
    except WorkPlanError as exc:
        await db.rollback();raise HTTPException(400,str(exc)) from exc


@router.post('/{session_id}/results/retry',name='diagnostic_results_retry')
async def retry_results(request:Request,session_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    from app.modules.assessment.repositories.diagnostic_result_repo import retry
    form=await request.form();csrf(request,form)
    try:
        session=await service.own(db,user,session_id,True)
        if session.results_published_at:raise WorkPlanError('Результаты уже опубликованы.')
        await retry(db,session.id);await db.commit()
        return RedirectResponse(request.url_for('diagnostic_progress',session_id=session_id),303)
    except WorkPlanError as exc:
        await db.rollback();raise HTTPException(400,str(exc)) from exc


async def result_context(db,user,session_id,attempt_id):
    from app.modules.assessment.services.diagnostic_report_service import report
    context=await report(db,attempt_id,user=user)
    if context['session']['id']!=session_id:raise WorkPlanError('Работа не найдена.')
    return context


@router.get('/{session_id}/attempt/{attempt_id}/result',name='diagnostic_attempt_result')
async def attempt_result(request:Request,session_id:int,attempt_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    try:
        context=await result_context(db,user,session_id,attempt_id)
        context.update(user=user,back_url=request.url_for('diagnostic_progress',session_id=session_id),
            image_url=request.url_for('diagnostic_result_image',session_id=session_id,attempt_id=attempt_id),
            review_url=request.url_for('diagnostic_manual_score',session_id=session_id,attempt_id=attempt_id),
            asset_url='/static/student_portal/work.css?v=113')
        return response(request,'student_portal/result.html',context)
    except WorkPlanError as exc:raise HTTPException(404,str(exc)) from exc


@router.post('/{session_id}/attempt/{attempt_id}/review',name='diagnostic_manual_score')
async def manual_result(request:Request,session_id:int,attempt_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    from app.modules.assessment.services.diagnostic_result_service import manual_score
    form=await request.form();csrf(request,form)
    try:
        await result_context(db,user,session_id,attempt_id)
        await manual_score(db,user,attempt_id,integer(form.get('answer_id'),1,2147483647),form.get('score'))
        await db.commit()
        return RedirectResponse(str(request.url_for('diagnostic_attempt_result',session_id=session_id,attempt_id=attempt_id))+'#answer-'+str(form.get('answer_id')),303)
    except WorkPlanError as exc:
        await db.rollback();raise HTTPException(400,str(exc)) from exc


@router.get('/{session_id}/attempt/{attempt_id}/image',name='diagnostic_result_image')
async def result_image(request:Request,session_id:int,attempt_id:int,object_key:str,db=Depends(get_db),user=Depends(require_bank_reader)):
    from app.modules.assessment.helpers.diagnostic_presentation import image_keys
    from app.core.storage import get_storage
    try:
        context=await result_context(db,user,session_id,attempt_id)
        if object_key not in image_keys(context['attempt']['presentation']):raise WorkPlanError('Изображение недоступно.')
        content=await get_storage().read(object_key=object_key,max_bytes=8_000_000)
    except (WorkPlanError,ValueError,OSError,FileNotFoundError):raise HTTPException(404,'Изображение недоступно.') from None
    mime={'png':'image/png','jpg':'image/jpeg','webp':'image/webp'}[object_key.rsplit('.',1)[1]]
    return Response(content,media_type=mime,headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


@router.get('/{session_id}/progress/options',name='diagnostic_progress_filter_options')
async def progress_filter_options(request:Request,session_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    from fastapi.responses import JSONResponse
    try:
        choices=await tracking.filter_choices(db,user,session_id,request.query_params)
        return JSONResponse(choices,headers={'Cache-Control':'no-store'})
    except WorkPlanError as exc:raise HTTPException(400,str(exc)) from exc


@router.post('/{session_id}/analytics/complete',name='diagnostic_analytics_complete')
async def complete_analytics(request:Request,session_id:int,db=Depends(get_db),user=Depends(require_bank_reader)):
    from app.modules.assessment.services.diagnostic_analytics_service import enqueue,overview
    from urllib.parse import parse_qsl
    form=await request.form();csrf(request,form)
    allowed={'district_id','school_id','class_id','subject_id','q','status','category','page_size','page'}
    saved={k:v for k,v in parse_qsl(str(form.get('return_query','')).lstrip('?').split('#',1)[0]) if k in allowed}
    target=str(request.url_for('diagnostic_progress',session_id=session_id))
    if saved:target+='?'+urlencode(saved)
    target+='#diagnostic-analytics'
    try:
        await enqueue(db,user,session_id,form);await db.commit()
        return RedirectResponse(target,303)
    except WorkPlanError as exc:
        await db.rollback()
        # Rollback expires ORM state even with expire_on_commit=False.
        # Reload explicitly before access checks and template rendering.
        await db.refresh(user)
        try:
            context=await tracking.progress(db,user,session_id,category=saved.get('category','all'),page=saved.get('page',1),values=saved)
            context['analytics_subjects']=await overview(db,session_id)
            for sub in context['analytics_subjects']:
                selected=form.get('analytics_'+str(sub['id']))
                if selected in dict(sub['options']):sub['selected_mode']=selected
            context.update(user=user,period_display=display,analytics_error=str(exc))
            result=response(request,'assessment/diagnostics/progress.html',context,400)
            await db.commit();return result
        except WorkPlanError:raise HTTPException(404,'Сессия недоступна. / Сессия қолжетімсіз.') from None
