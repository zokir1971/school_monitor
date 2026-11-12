"""Localized staff web diagnostics without changing personnel operations."""
import re
from starlette.responses import JSONResponse
from app.core.i18n import resolve_language, translate
from app.core.staff_ui_messages import STAFF_ERROR_MESSAGES
from app.core.assessment_i18n import application_http_exception_handler


def is_staff_request(request):
    path = request.scope['path'].rstrip('/')
    return path == '/staff/school' or path.startswith('/staff/school/')


def staff_message(request, value, status_code=400):
    language = resolve_language(request)
    value = str(value or '')
    if value in STAFF_ERROR_MESSAGES:
        return translate(value, language)
    match = re.fullmatch(r'Импорт: создано (\d+), обновлено (\d+), пропущено (\d+), ошибок (\d+)', value)
    if match:
        text = translate('Импорт: создано {created}, обновлено {updated}, пропущено {skipped}, ошибок {errors}', language)
        return text.format(**dict(zip(('created','updated','skipped','errors'), match.groups())))
    if value.startswith('Некорректное число'):
        return translate('Проверьте числовые значения.', language)
    if value.startswith('Некорректная дата:'):
        return translate('Проверьте дату.', language)
    if value.startswith('Недопустимая роль:'):
        return translate('Недопустимая роль', language)
    message = {401:'Войдите в систему для продолжения.',403:'Нет доступа к управлению сотрудниками.',
               404:'Сотрудник не найден',422:'Проверьте обязательные поля и формат значений.'}.get(
                   status_code,'Не удалось выполнить действие. Проверьте данные сотрудника.')
    return translate(message, language)


async def staff_http_exception_handler(request, exc):
    if not is_staff_request(request):
        return await application_http_exception_handler(request, exc)
    return JSONResponse(status_code=exc.status_code,
        content={'detail':staff_message(request, exc.detail, exc.status_code)},
        headers={**(exc.headers or {}),'Content-Language':resolve_language(request),
                 'Cache-Control':'no-store','Vary':'Cookie'})


def staff_validation_response(request, errors):
    message = staff_message(request, None, 422)
    return JSONResponse(status_code=422, content={'detail':[
        {'loc':error.get('loc',[]),'type':error.get('type','value_error'),'msg':message}
        for error in errors], 'message':message},
        headers={'Content-Language':resolve_language(request),'Cache-Control':'no-store','Vary':'Cookie'})
