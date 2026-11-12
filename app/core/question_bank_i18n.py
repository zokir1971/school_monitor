"""Translate errors only at the Question Bank web boundary, preserving status codes."""
from fastapi.exception_handlers import http_exception_handler
from starlette.responses import JSONResponse
from app.core.i18n import catalog, resolve_language, translate
from app.core.question_bank_ui_messages import QB_UI_MESSAGES, QB_ENUM_MESSAGES

from app.core.bilingual_ui_messages import BILINGUAL_MESSAGES
KNOWN_UI_MESSAGES = frozenset(QB_UI_MESSAGES) | frozenset(QB_ENUM_MESSAGES) | frozenset(BILINGUAL_MESSAGES)


def is_question_bank_request(request):
    path = request.scope['path'].rstrip('/')
    return (path == '/teacher/question-bank' or path.startswith('/teacher/question-bank/')
            or path == '/assessment/question-bank/expert/review'
            or path.startswith('/assessment/question-bank/expert/review/')
            or path == '/ai/create' or path.startswith('/ai/runs/'))


def error_message(request, detail, status_code):
    language = resolve_language(request)
    if isinstance(detail, str):
        text = catalog(language).gettext(detail)
        # A known Russian-source message may intentionally equal its source in RU.
        if detail in KNOWN_UI_MESSAGES:
            return text
    fallback = {
        401: 'Войдите в систему для продолжения.',
        403: 'Нет доступа к этому действию или заданию.',
        404: 'Задание или ресурс не найдены либо недоступны.',
        422: 'Проверьте заполнение обязательных полей и формат значений.',
    }.get(status_code, 'Не удалось выполнить действие. Проверьте поля и параметры задания.')
    return translate(fallback, language)


async def question_bank_http_exception_handler(request, exc):
    if not is_question_bank_request(request):
        return await http_exception_handler(request, exc)
    return JSONResponse(status_code=exc.status_code,
        content={'detail': error_message(request, exc.detail, exc.status_code)},
        headers={**(exc.headers or {}), 'Content-Language': resolve_language(request),
                 'Cache-Control': 'no-store', 'Vary': 'Cookie'})


def question_bank_validation_response(request, errors):
    return JSONResponse(status_code=422, content={
        'detail': [{'loc': error.get('loc', []), 'type': error.get('type', 'value_error'),
                    'msg': error_message(request, None, 422)} for error in errors],
        'message': error_message(request, None, 422)},
        headers={'Content-Language': resolve_language(request), 'Cache-Control': 'no-store',
                 'Vary': 'Cookie'})
