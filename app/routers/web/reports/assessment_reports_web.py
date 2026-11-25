"""Two system reports, one authorized lifecycle. Report kind comes from the route."""
from urllib.parse import urlsplit
from fastapi import APIRouter,Depends,Request,HTTPException
from fastapi.responses import RedirectResponse
from app.db.session import get_db
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.routers.web.web_common import templates
from app.routers.web.helpers.render import render
from app.routers.web.jinja_filters import MONTH_NAMES_KZ
from app.core.i18n import resolve_language
from app.core.storage.factory import get_storage
from app.modules.reports.services import assessment_report_service as reports
from app.modules.reports.services import assessment_report_document_service as documents
from app.modules.reports.repositories import assessment_report_repo as repo
from app.modules.reports.assessment_report_types import REPORT_TYPES

router=APIRouter(prefix='/staff/reports',tags=['assessment-system-reports'])
allowed=require_roles(UserRole.SCHOOL_ADMIN,UserRole.SCHOOL_STAFF)


def show(request,user,page,*,snapshot=None,error=None,status=200):
    language=resolve_language(request,user)
    code=page['context']['report_code'];config=REPORT_TYPES[code]
    doc=page['document'];saved=(doc or {}).get('schema_json') or {}
    snapshot=None if page.get('form_restored') else snapshot or (saved if reports.is_snapshot(saved,code) else None)
    if not assessment_enabled() and snapshot_has_assessment(snapshot):snapshot=None
    readonly=False;readonly_reason=None;report_finalized=False
    try:documents.ensure_editable(page)
    except reports.QualityReportError as exc:
        readonly=True;readonly_reason=reports.error_message(exc,language);report_finalized=getattr(exc,'report_finalized',False)
    readonly_success=bool((report_finalized or request.query_params.get('completed')=='1') and not error and doc and doc.get('file_path')
        and reports.value(doc['status']) in ('submitted','approved','accepted') and reports.is_snapshot(saved,code))
    can_refresh_pdf=False
    try:
        documents.ensure_pdf_refreshable(page);can_refresh_pdf=True
    except reports.QualityReportError:pass
    completion_success=bool(readonly_success and request.query_params.get('completed')=='1')
    response=render(templates,request,('staff/reports/structured_report_fill.html' if config.get('structured') else 'staff/reports/quality_report_fill.html'),dict(user=user,page=page,
        inspection_definitions=reports.INSPECTION_SECTIONS,inspection_documents=reports.INSPECTION_DOCUMENTS,inspection_visit_purposes=reports.INSPECTION_VISIT_PURPOSES,MONTH_NAMES=MONTH_NAMES_KZ,snapshot=snapshot,readonly=readonly,readonly_reason=readonly_reason,readonly_success=readonly_success,can_refresh_pdf=can_refresh_pdf,pdf_revision=documents.pdf_revision(doc),refresh_route=config['route']+'_fill_submit',pdf_updated=request.query_params.get('pdf_updated')=='1',revision=saved.get('revision',0),error=reports.error_message(error,language),error_field=getattr(error,'field',None),completion_success=completion_success,
        report_code=code,report_title=config['title_ru' if language=='ru' else 'title_kk'],
        fill_route=config['route']+'_fill_page',pdf_route=config['route']+'_pdf_view'),status_code=status)
    response.headers['Cache-Control']='no-store'
    return response


from app.core.feature_access import report_dependency
from app.core.feature_flags import snapshot_has_assessment,assessment_enabled

def register_report(code,config):
    path=config['path'];name=config['route']
    async def fill(request:Request,month_item_id:int,selected_report_id:int,db=Depends(get_db),user=Depends(allowed)):
        try:
            page=await reports.load(db,user,month_item_id,selected_report_id,request.query_params,report_code=code)
            doc=page['document'];saved=(doc or {}).get('schema_json') or {}
            # Old draft snapshots lack grouped goals/math segments and new metrics.
            # Refresh only the preview, never write on GET or alter finalized reports.
            if (not request.query_params and doc and reports.value(doc['status']) in ('draft','rejected')
                    and reports.is_snapshot(saved,code) and saved.get('report_layout_version',0)<160):
                try:
                    documents.ensure_editable(page)
                except reports.QualityReportError:
                    return show(request,user,page)
                try:
                    snapshot=await reports.calculate(db,user,page,saved,saved.get('language') or resolve_language(request,user))
                except reports.QualityReportError as exc:
                    return show(request,user,page,error=exc,status=400)
                return show(request,user,page,snapshot=snapshot)
            return show(request,user,page)
        except reports.QualityReportError as exc:raise HTTPException(400,reports.error_message(exc,resolve_language(request,user))) from exc

    async def submit(request:Request,month_item_id:int,selected_report_id:int,db=Depends(get_db),user=Depends(allowed)):
        origin=request.headers.get('origin')
        if origin:
            actual=urlsplit(origin);expected=urlsplit(str(request.base_url))
            if (actual.scheme,actual.netloc)!=(expected.scheme,expected.netloc):raise HTTPException(403,'Cross-origin request rejected')
        params=await request.form(max_fields=12000)
        action=params.get('action')
        if action is None and params.get('refresh') and code in ('class_summary','teacher_analysis'):action='filter'
        if action not in ('preview','save','complete','refresh_pdf','filter','next_page','previous_page','add_page','assemble','new_version'):raise HTTPException(400,'Unknown action')
        if action in ('assemble','new_version') and code!='analytical_reference':raise HTTPException(400,'Unknown action')
        if action in ('next_page','previous_page','add_page') and not config.get('structured'):raise HTTPException(400,'Unknown action')
        page=None
        try:
            page=await reports.load(db,user,month_item_id,selected_report_id,params,lock=action not in ('preview','filter'),report_code=code)
            if action=='filter':
                if params.get('language_draft_token'):
                    documents.ensure_editable(page)
                    doc=page['document'] or {};saved=doc.get('schema_json') or {}
                    token=str(params['language_draft_token'])
                    if (len(token)!=32 or any(c not in '0123456789abcdef' for c in token)
                            or reports.integer(params.get('language_draft_document_id'),0)!=doc.get('id',0)
                            or reports.integer(params.get('revision'),0)!=saved.get('revision',0)):
                        raise reports.QualityReportError('Отчёт изменился. Откройте актуальную версию; временная копия формы сохранена в этой вкладке. / Есеп өзгерді. Өзекті нұсқасын ашыңыз; пішіннің уақытша көшірмесі осы қойындыда сақталған.')
                    page.update(form_restored=True,language_draft_token=token)
                return show(request,user,page)
            if action=='refresh_pdf':
                await documents.save(db,user,page,params,(page['document'] or {}).get('schema_json') or {},request,templates,refresh_pdf=True)
                return RedirectResponse(str(request.url_for(name+'_fill_page',month_item_id=month_item_id,selected_report_id=selected_report_id))+'?pdf_updated=1',303)
            if action=='new_version':
                await documents.start_final_draft(db,user,page,params)
                return RedirectResponse(str(request.url_for(name+'_fill_page',month_item_id=month_item_id,selected_report_id=selected_report_id)),303)
            documents.ensure_editable(page)
            language=str(params.get('document_language') or resolve_language(request,user))
            if language not in ('ru','kk'):raise reports.QualityReportError('Выберите язык документа. / Құжат тілін таңдаңыз.')
            snapshot=await reports.calculate(db,user,page,params,language)
            if action=='preview':
                page['preview_ready']=True
                return show(request,user,page,snapshot=snapshot)
            await documents.save(db,user,page,params,snapshot,request,templates,complete=action=='complete')
            target=str(request.url_for(name+'_fill_page',month_item_id=month_item_id,selected_report_id=selected_report_id))
            if action in ('next_page','previous_page','add_page'):
                current=reports.integer(params.get('entry_page'),1)
                number=current+1 if action!='previous_page' else max(1,current-1)
                target+='?entry_page='+str(number)
            if action=='complete':target+='?completed=1#report-feedback'
            return RedirectResponse(target,303)
        except reports.QualityReportError as exc:
            await db.rollback()
            await db.refresh(user)
            if page:return show(request,user,page,error=exc,status=400)
            raise HTTPException(400,reports.error_message(exc,resolve_language(request,user))) from exc

    async def pdf(report_id:int,db=Depends(get_db),user=Depends(allowed)):
        doc=await repo.document_by_id(db,report_id,report_code=code)
        if doc is None:raise HTTPException(404,'Report not found')
        context=await repo.context(db,task_id=doc['month_item_id'],selected_id=doc['selected_report_id'] or 0,user=user,report_code=code)
        if context is None:raise HTTPException(404,'Report not found')
        if not assessment_enabled() and snapshot_has_assessment(doc.get('schema_json') or {}):
            from app.core.feature_access import FeatureUnavailable
            raise FeatureUnavailable()
        if not doc['file_path']:raise HTTPException(404,'PDF not found')
        storage=get_storage()
        if not await storage.exists(object_key=doc['file_path']):raise HTTPException(404,'PDF not found')
        return RedirectResponse(await storage.get_download_url(object_key=doc['file_path'],expires_in=300),302,headers={'Cache-Control':'no-store'})

    router.add_api_route('/{month_item_id}/templates/{selected_report_id}/'+path+'/fill',fill,methods=['GET'],dependencies=[Depends(report_dependency(code))],name=name+'_fill_page')
    router.add_api_route('/{month_item_id}/templates/{selected_report_id}/'+path+'/fill',submit,methods=['POST'],dependencies=[Depends(report_dependency(code))],name=name+'_fill_submit')
    router.add_api_route('/'+path+'/{report_id}/pdf',pdf,methods=['GET'],dependencies=[Depends(report_dependency(code))],name=name+'_pdf_view')


for report_code,definition in REPORT_TYPES.items():register_report(report_code,definition)
