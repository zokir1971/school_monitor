"""Localized Assessment web errors, independent of grading and assessment data."""
from starlette.responses import JSONResponse
from app.core.i18n import resolve_language, translate
from app.core.assessment_ui_messages import ASSESSMENT_UI_MESSAGES
from app.core.question_bank_i18n import question_bank_http_exception_handler

KNOWN_MESSAGES = frozenset(ASSESSMENT_UI_MESSAGES)
PREFIXES = ('/teacher/assessment', '/staff/assessment', '/region/assessment', '/district/assessment')


def is_assessment_request(request):
    path = request.scope['path'].rstrip('/')
    return any(path == prefix or path.startswith(prefix + '/') for prefix in PREFIXES)


def assessment_error_message(request, detail, status_code):
    language = resolve_language(request)
    # Expert administration is under /region/assessment but has its own diagnostics.
    prefix = '/region/assessment/question-bank/experts'
    path = request.scope['path'].rstrip('/')
    if path == prefix or path.startswith(prefix + '/'):
        from app.core.expert_ui_messages import EXPERT_ERROR_MESSAGES
        if isinstance(detail, str) and detail in EXPERT_ERROR_MESSAGES:
            return translate(detail, language)
        message = {
            401: 'Войдите в систему для продолжения.',
            403: 'Нет доступа к управлению экспертами.',
            404: 'Сарапшы табылмады.',
            422: 'Проверьте обязательные поля и формат значений.',
        }.get(status_code, 'Не удалось выполнить действие. Проверьте данные эксперта и выбранные правила.')
        return translate(message, language)
    # Expert administration is under /region/assessment but has its own diagnostics.
    prefix = '/region/assessment/question-bank/experts'
    path = request.scope['path'].rstrip('/')
    if path == prefix or path.startswith(prefix + '/'):
        from app.core.expert_ui_messages import EXPERT_ERROR_MESSAGES
        if isinstance(detail, str) and detail in EXPERT_ERROR_MESSAGES:
            return translate(detail, language)
        message = {
            401: 'Войдите в систему для продолжения.',
            403: 'Нет доступа к управлению экспертами.',
            404: 'Сарапшы табылмады.',
            422: 'Проверьте обязательные поля и формат значений.',
        }.get(status_code, 'Не удалось выполнить действие. Проверьте данные эксперта и выбранные правила.')
        return translate(message, language)
    if status_code==400 and path in ('/staff/assessment/create','/teacher/assessment/create'):
        from app.core.manual_assessment_errors import creation_message
        message=creation_message(detail,language)
        if message is not None:return message
    if isinstance(detail, str) and detail in KNOWN_MESSAGES:
        return translate(detail, language)
    message = {
        401: 'Войдите в систему для продолжения.',
        403: 'Нет доступа к этой оценочной работе или результатам.',
        404: 'Оценочная работа или результаты не найдены.',
        422: 'Проверьте обязательные поля и формат значений.',
    }.get(status_code, 'Не удалось выполнить действие. Проверьте параметры оценочной работы и введённые результаты.')
    return translate(message, language)


async def application_http_exception_handler(request, exc):
    if not is_assessment_request(request):
        return await question_bank_http_exception_handler(request, exc)
    return JSONResponse(status_code=exc.status_code,
        content={'detail': assessment_error_message(request, exc.detail, exc.status_code)},
        headers={**(exc.headers or {}), 'Content-Language': resolve_language(request),
                 'Cache-Control': 'no-store', 'Vary': 'Cookie'})


def assessment_validation_response(request, errors):
    message = assessment_error_message(request, None, 422)
    return JSONResponse(status_code=422, content={
        'detail': [{'loc': error.get('loc', []), 'type': error.get('type', 'value_error'),
                    'msg': message} for error in errors], 'message': message},
        headers={'Content-Language': resolve_language(request), 'Cache-Control': 'no-store', 'Vary': 'Cookie'})
