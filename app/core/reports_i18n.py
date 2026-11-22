"""Known report workflow feedback, independent of report content and operations."""
import re
from starlette.responses import JSONResponse
from app.core.i18n import resolve_language,translate
from app.core.reports_ui_messages import REPORTS_ERROR_MESSAGES,REPORTS_FEEDBACK_MESSAGES,REPORTS_WORKFLOW_TRANSLATIONS
from app.core.execution_i18n import execution_http_exception_handler


def is_reports_request(request):
    path=request.scope['path'].rstrip('/')
    return path=='/staff/reports' or path.startswith('/staff/reports/')


def reports_message(request,value,status_code=400):
    from app.core.report_forms_ui_messages import REPORT_FORM_ERROR_MESSAGES
    from app.core.template_constructor_ui_messages import CONSTRUCTOR_ERROR_MESSAGES
    from app.core.report_completion_i18n import COMPLETION_FEEDBACK_MESSAGES
    from app.core.report_pdf_i18n import DOCUMENT_LANGUAGE_ERROR
    language=resolve_language(request)
    from app.modules.reports.rules.notebook_classes import MESSAGES
    if isinstance(value, str) and value in MESSAGES:
        return MESSAGES[value] if language == 'kk' else value
    if isinstance(value, str) and value in REPORTS_WORKFLOW_TRANSLATIONS:
        return REPORTS_WORKFLOW_TRANSLATIONS[value] if language == "kk" else value
    if isinstance(value,str) and value in (*REPORTS_ERROR_MESSAGES,*REPORTS_FEEDBACK_MESSAGES,*REPORT_FORM_ERROR_MESSAGES,*CONSTRUCTOR_ERROR_MESSAGES,*COMPLETION_FEEDBACK_MESSAGES,DOCUMENT_LANGUAGE_ERROR):
        return translate(value,language)
    if isinstance(value,str):
        match=re.fullmatch(r'Распределение отчётов сохранено\. Создано: (\d+), изменено: (\d+), без изменений: (\d+)\.',value)
        if match:
            source='Распределение отчётов сохранено. Создано: {created}, изменено: {updated}, без изменений: {unchanged}.'
            return translate(source,language).format(**dict(zip(('created','updated','unchanged'),match.groups())))
        if value.startswith('Тип отчета не поддерживается:'):
            return translate('Тип отчета не поддерживается.',language)
    source={401:'Войдите в систему для продолжения.',403:'Нет доступа к этому отчёту или шаблону.',
            404:'Отчёт или шаблон не найден.',422:'Проверьте обязательные поля и формат значений.'}.get(
                status_code,'Не удалось выполнить действие. Проверьте отчёт и выбранных исполнителей.')
    return translate(source,language)


async def reports_http_exception_handler(request,exc):
    if not is_reports_request(request):
        return await execution_http_exception_handler(request,exc)
    return JSONResponse(status_code=exc.status_code,content={'detail':reports_message(request,exc.detail,exc.status_code)},
        headers={**(exc.headers or {}),'Content-Language':resolve_language(request),'Cache-Control':'no-store','Vary':'Cookie'})


def reports_validation_response(request,errors):
    message=reports_message(request,None,422)
    return JSONResponse(status_code=422,content={'detail':[
        {'loc':error.get('loc',[]),'type':error.get('type','value_error'),'msg':message} for error in errors],
        'message':message},headers={'Content-Language':resolve_language(request),'Cache-Control':'no-store','Vary':'Cookie'})
