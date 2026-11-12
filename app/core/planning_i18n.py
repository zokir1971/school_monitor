"""School planning HTTP diagnostics, independent of plan data and archive rules."""
from starlette.responses import JSONResponse
from app.core.i18n import resolve_language, translate
from app.core.planning_ui_messages import PLANNING_EXTRA_MESSAGES
from app.core.staff_i18n import staff_http_exception_handler


def is_planning_request(request):
    path = request.scope['path'].rstrip('/')
    return path == '/planning/school' or path.startswith('/planning/school/')


def planning_message(request, value, status_code=400):
    language = resolve_language(request)
    from app.core.monthly_ui_messages import MONTHLY_SYSTEM_MESSAGES
    if isinstance(value, str) and value in (*PLANNING_EXTRA_MESSAGES, *MONTHLY_SYSTEM_MESSAGES):
        return translate(value, language)
    message = {401:'Войдите в систему для продолжения.',403:'Нет доступа к этому плану.',
               404:'План не найден',422:'Проверьте обязательные поля и формат значений.'}.get(
                   status_code, 'Не удалось выполнить действие. Проверьте параметры плана.')
    return translate(message, language)


async def planning_http_exception_handler(request, exc):
    if not is_planning_request(request):
        return await staff_http_exception_handler(request, exc)
    return JSONResponse(status_code=exc.status_code,
        content={'detail':planning_message(request, exc.detail, exc.status_code)},
        headers={**(exc.headers or {}),'Content-Language':resolve_language(request),
                 'Cache-Control':'no-store','Vary':'Cookie'})


def planning_validation_response(request, errors):
    message = planning_message(request, None, 422)
    return JSONResponse(status_code=422, content={'detail':[
        {'loc':error.get('loc',[]),'type':error.get('type','value_error'),'msg':message}
        for error in errors], 'message':message},
        headers={'Content-Language':resolve_language(request),'Cache-Control':'no-store','Vary':'Cookie'})
