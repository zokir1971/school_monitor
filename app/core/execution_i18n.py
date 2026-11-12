"""Localized execution UI diagnostics; task and document operations stay unchanged."""
from starlette.responses import JSONResponse
from app.core.i18n import resolve_language,translate
from app.core.execution_ui_messages import EXECUTION_ERROR_MESSAGES
from app.core.planning_i18n import planning_http_exception_handler


def is_execution_request(request):
    path=request.scope['path'].rstrip('/')
    return path=='/staff/tasks' or path.startswith('/staff/tasks/')


def execution_message(request,value,status_code=400):
    from app.core.reports_ui_messages import REPORTS_ERROR_MESSAGES
    if isinstance(value,str) and value in (*EXECUTION_ERROR_MESSAGES,*REPORTS_ERROR_MESSAGES):
        return translate(value,resolve_language(request))
    source={401:'Войдите в систему для продолжения.',403:'Нет доступа к этой задаче.',
            404:'Задача не найдена или недоступна.',422:'Проверьте обязательные поля и формат значений.'}.get(
                status_code,'Не удалось выполнить действие. Проверьте задачу и параметры выполнения.')
    return translate(source,resolve_language(request))


async def execution_http_exception_handler(request,exc):
    if not is_execution_request(request):
        return await planning_http_exception_handler(request,exc)
    return JSONResponse(status_code=exc.status_code,content={'detail':execution_message(request,exc.detail,exc.status_code)},
        headers={**(exc.headers or {}),'Content-Language':resolve_language(request),'Cache-Control':'no-store','Vary':'Cookie'})


def execution_validation_response(request,errors):
    message=execution_message(request,None,422)
    return JSONResponse(status_code=422,content={'detail':[
        {'loc':error.get('loc',[]),'type':error.get('type','value_error'),'msg':message} for error in errors],
        'message':message},headers={'Content-Language':resolve_language(request),'Cache-Control':'no-store','Vary':'Cookie'})
