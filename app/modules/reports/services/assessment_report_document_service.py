"""Transactional document lifecycle using the existing VSK storage/signature flow."""
import hashlib
import logging
import re
from uuid import uuid4
from datetime import datetime,timezone,timedelta
from app.modules.reports.repositories import assessment_report_repo as repo
from app.modules.reports.services import assessment_report_service as reports
from app.modules.reports.repositories.report_verify_repo import ReportVerifyRepo
from app.modules.reports.repositories.document_correction_repo import DocumentCorrectionRepo
from app.modules.reports.utils.report_signature import ReportSignatureService
from app.core.storage.factory import get_storage
from app.core.storage.school_storage import SchoolStorageService

logger=logging.getLogger(__name__)


def ensure_editable(page):
    context=page['context'];doc=page['document']
    if not context['can_edit'] or context['assigned_staff_id'] is None:
        raise reports.QualityReportError('Отчёт должен быть назначен исполнителю. / Есеп орындаушыға тағайындалуы тиіс.')
    if any(reports.value(context.get(key))=='archived' for key in ('month_status','annual_status')):
        raise reports.QualityReportError('Архивный отчёт изменять нельзя. / Мұрағаттағы есепті өзгертуге болмайды.')
    if context['completed_at']:
        raise reports.QualityReportError('Задача завершена. Отчёт доступен только для просмотра. / Тапсырма аяқталған. Есеп тек қарауға қолжетімді.')
    # This page already has an authorized selected system report. The existing
    # execution flow records completion_mode only when the whole task finishes;
    # an unset mode must not prevent its assigned reports from being prepared.
    mode=reports.value(context['completion_mode'])
    if mode not in (None,'','final_with_system_reports'):
        raise reports.QualityReportError('Выбранный способ завершения задачи не предусматривает системные отчёты. / Таңдалған аяқтау тәсілінде жүйелік есептер қарастырылмаған.')
    if reports.value(context['assignment_status'])=='waived':
        raise reports.QualityReportError('Выполнение отчёта отменено ответственным. / Жауапты тұлға есепті орындаудан босатқан.')
    if doc and reports.value(doc['status']) not in ('draft','rejected'):
        error=reports.QualityReportError('Завершённый отчёт зафиксирован и доступен для просмотра. / Аяқталған есеп бекітілген, оны қарауға болады.')
        error.report_finalized=reports.value(doc['status']) in ('submitted','approved','accepted')
        raise error
    if doc and doc.get('report_code') not in (None,context.get('report_code',repo.CODE)):
        raise reports.QualityReportError('Тип документа не соответствует выбранному отчёту. / Құжат түрі таңдалған есепке сәйкес емес.')
    if doc and doc['source']!='generated':
        raise reports.QualityReportError('Для выбранного отчёта уже используется другой источник документа. / Таңдалған есеп басқа құжат көзін қолданады.')


def pdf_revision(document):
    if not document:return ''
    return hashlib.sha256((str(document['id'])+'|'+str(document.get('file_path') or '')).encode()).hexdigest()


def ensure_pdf_refreshable(page):
    context=page['context'];doc=page['document'];code=context.get('report_code',repo.CODE)
    if not context['can_edit'] or reports.value(context.get('assignment_status'))=='waived':
        raise reports.QualityReportError('Обновить PDF может назначенный исполнитель или администратор школы. / PDF файлын тағайындалған орындаушы немесе мектеп әкімшісі жаңарта алады.')
    if any(reports.value(context.get(key))=='archived' for key in ('month_status','annual_status')):
        raise reports.QualityReportError('Архивный отчёт изменять нельзя. / Мұрағаттағы есепті өзгертуге болмайды.')
    if (not doc or reports.value(doc['status']) not in ('submitted','approved','accepted')
            or reports.value(doc['source'])!='generated' or doc.get('report_code') not in (None,code)
            or not doc.get('file_path') or not reports.is_snapshot(doc.get('schema_json') or {},code)):
        raise reports.QualityReportError('Обновление PDF доступно для завершённого системного отчёта с сохранёнными данными. / PDF жаңарту сақталған деректері бар аяқталған жүйелік есеп үшін қолжетімді.')


def body(templates,snapshot,**extra):
    return templates.get_template('staff/reports/quality_report_body.html').render(snapshot=snapshot,ru=snapshot['language']=='ru',**extra)


async def make_pdf(html):
    from app.core.report_pdf_renderer import render_report_pdf
    # The shared style template includes MathLive for interactive previews.
    # A PDF without math fields needs neither its CDN script nor its fonts.
    # Be conservative: even a tag inside a comment keeps the dependency.
    if not re.search(r'<math-field(?=[\s/>])', html, flags=re.IGNORECASE):
        html = html.replace('<script defer src="https://cdn.jsdelivr.net/npm/mathlive"></script>', '')
    return await render_report_pdf(html, structured=True)


async def save(db,user,page,params,snapshot,request,templates,*,complete=False,refresh_pdf=False):
    from app.core.feature_flags import assessment_enabled,snapshot_has_assessment
    from app.core.feature_access import ensure_report,FeatureUnavailable
    ensure_report(page['context']['report_code'])
    if not assessment_enabled() and snapshot_has_assessment(snapshot):raise FeatureUnavailable()
    if refresh_pdf:ensure_pdf_refreshable(page)
    else:ensure_editable(page)
    previous=page['document'];expected=reports.integer(params.get('revision'),0)
    current=((previous or {}).get('schema_json') or {}).get('revision',0)
    if expected!=current:raise reports.QualityReportError('Отчёт изменён в другой вкладке. Обновите страницу. / Есеп басқа қойындыда өзгертілді. Бетті жаңартыңыз.')
    code=page['context'].get('report_code',repo.CODE)
    if not reports.is_snapshot(snapshot,code):raise reports.QualityReportError('Report type mismatch')
    if code=='analytical_reference' and snapshot.get('assembly_version')==1 and reports.integer(params.get('document_id'),0)!=(previous or {}).get('id',0):
        raise reports.QualityReportError('Версия документа изменилась. Обновите страницу. / Құжат нұсқасы өзгерді. Бетті жаңартыңыз.')
    if refresh_pdf:
        if reports.integer(params.get('document_id'))!=previous['id'] or params.get('pdf_revision')!=pdf_revision(previous):
            raise reports.QualityReportError('PDF уже изменён. Обновите страницу. / PDF өзгертілген. Бетті жаңартыңыз.')
        snapshot=previous['schema_json']
    else:
        snapshot=dict(snapshot,revision=current+1)
        if complete and code=='analytical_reference' and snapshot.get('assembly_version')==1:
            snapshot['signed_by']=dict(user_id=user.id,full_name=user.full_name)
            snapshot['signed_at']=datetime.now(timezone.utc).isoformat()
    storage=None;new_key=None;commit_started=False
    try:
        if refresh_pdf:
            doc_id=previous['id']
        else:
            html=body(templates,snapshot)
            doc_id=await repo.save_document(db,context=page['context'],user=user,payload=snapshot,html=html,
                text=snapshot['conclusion']+'\n'+snapshot['recommendations'])
            await repo.link_assessments(db,page['context']['task_id'],[r['assessment_id'] for r in snapshot['rows']],user.id)
        if complete or refresh_pdf:
            at=datetime.now(timezone.utc)
            signature=(await ReportVerifyRepo.get_active_signature_for_document(db,report_type=code,document_id=doc_id)) if refresh_pdf else None
            if signature is None:
                token=ReportSignatureService.create_token(report_type=code,report_id=doc_id,document_id=doc_id)
                await ReportVerifyRepo.deactivate_old_signatures(db,report_type=code,report_id=doc_id,document_id=doc_id)
                signature=await ReportVerifyRepo.create_signature_token(db,token=token,report_type=code,report_id=doc_id,document_id=doc_id)
            qr=ReportSignatureService.generate_qr_data_uri(verify_url=str(request.url_for('report_verify_by_code_page',code=signature.code)))
            signed_at=(datetime.fromisoformat(snapshot['signed_at']) if snapshot.get('signed_at') else previous.get('submitted_at')) if refresh_pdf else at
            # Refreshing the file does not re-date the completed report.
            signature_info=dict(report_id=doc_id,date=(signed_at.astimezone(timezone(timedelta(hours=5))).strftime('%d.%m.%Y %H:%M') if isinstance(signed_at,datetime) else '—'))
            html=templates.get_template('staff/reports/quality_report_pdf.html').render(snapshot=snapshot,ru=snapshot['language']=='ru',qr=qr,signature_info=signature_info)
            pdf=await make_pdf(html)
            context=await repo.storage_context(db,page['context']['task_id'],user.school_id)
            storage=SchoolStorageService(storage=get_storage())
            stored=await storage.save_task_report(context=context,document_id=doc_id,report_code=code+'_pdf_'+uuid4().hex,content=pdf,
                original_file_name=f'{code}_{doc_id}.pdf',content_type='application/pdf')
            new_key=stored.object_key
            if refresh_pdf:
                if not await repo.replace_pdf_file(db,previous,stored):
                    raise reports.QualityReportError('PDF изменён другим пользователем. Обновите страницу. / PDF файлын басқа пайдаланушы өзгерткен. Бетті жаңартыңыз.')
            else:await repo.submit_document(db,doc_id,page['context']['selected_id'],user.id,at,stored)
        commit_started=True
        await db.commit()
    except BaseException as exc:
        await db.rollback()
        remove_new=not commit_started
        if new_key and commit_started:
            # A lost commit response must not cause deletion of the active file.
            try:
                current_doc=await repo.document(db,page['context']['selected_id'],task_id=page['context']['task_id'],report_code=code)
                remove_new=not current_doc or current_doc.get('file_path')!=new_key
                await db.rollback()
            except Exception:
                logger.exception('Commit outcome unknown; preserving uploaded PDF')
                remove_new=False
        if new_key and remove_new:
            try:await get_storage().delete(object_key=new_key)
            except Exception:logger.exception('Could not clean failed quality report upload')
        if refresh_pdf and isinstance(exc,Exception) and not isinstance(exc,reports.QualityReportError):
            logger.exception('PDF refresh failed')
            raise reports.QualityReportError('Не удалось обновить PDF. Обновите страницу и повторите действие. / PDF жаңарту сәтсіз аяқталды. Бетті жаңартып, қайталаңыз.') from exc
        raise
    old_key=(previous or {}).get('file_path')
    if (complete or refresh_pdf) and old_key and new_key and old_key!=new_key and old_key.startswith('schools/'):
        try:
            if not await DocumentCorrectionRepo.referenced(db,old_key):
                await get_storage().delete(object_key=old_key)
        except Exception:logger.exception('Could not remove replaced quality report file')
    return doc_id


async def start_final_draft(db,user,page,params):
    """Explicit version creation, under the task lock acquired by reports.load."""
    context=page['context'];previous=page['document']
    if (context['report_code']!='analytical_reference' or not context['can_edit']
            or context['completed_at'] or any(reports.value(context.get(k))=='archived' for k in ('month_status','annual_status'))
            or not previous or previous['source']!='generated'
            or reports.value(previous['status']) not in ('submitted','approved','accepted')
            or (previous.get('schema_json') or {}).get('assembly_version')!=1):
        raise reports.QualityReportError('Создание новой версии недоступно. / Жаңа нұсқа жасау қолжетімсіз.')
    if (reports.integer(params.get('document_id'))!=previous['id']
            or reports.integer(params.get('revision'),0)!=(previous.get('schema_json') or {}).get('revision',0)):
        raise reports.QualityReportError('Документ изменился. Обновите страницу. / Құжат өзгерді. Бетті жаңартыңыз.')
    result=await repo.new_final_draft(db,previous=previous,user=user)
    await db.commit()
    return result
