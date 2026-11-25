"""Language-neutral notice codes in redirects; translate at the GET render."""
import re
from fastapi import HTTPException
from app.core.i18n import resolve_language
from app.core.ui_locale_context import ui_locale

REASONS = {
    'status': ('статус задачи — {status}', 'тапсырма мәртебесі — {status}'),
    'completed': ('есть фактическая дата или отметка завершения', 'нақты орындалу күні немесе аяқталу белгісі бар'),
    'assigned': ('назначены исполнители', 'орындаушылар тағайындалған'),
    'execution': ('есть запись выполнения', 'орындалу жазбасы бар'),
    'execution_data': ('есть параметры выполнения/алгоритм', 'орындау параметрлері/алгоритмі бар'),
    'documents': ('есть отчёты или документы', 'есептер немесе құжаттар бар'),
    'review': ('есть результат рассмотрения', 'қарау нәтижесі бар'),
    'published_included': ('задача включена в отправленный или архивный месячный план', 'тапсырма жіберілген немесе мұрағатталған айлық жоспарға енгізілген'),
}
MESSAGES = {
    'archived_plan': ('Архивный план изменять нельзя.', 'Мұрағатталған жоспарды өзгертуге болмайды.'),
    'documents': ('У строки есть документы. История сохранена.', 'Жолдың құжаттары бар. Тарих сақталды.'),
    'foreign_month': ('Связь месячной задачи с годовым планом некорректна.', 'Айлық тапсырманың жылдық жоспармен байланысы дұрыс емес.'),
    'custom_only': ('Удалять можно только добавленные пользователем строки. Для строки шаблона используйте «Исключить из плана».', 'Тек пайдаланушы қосқан жолдарды жоюға болады. Үлгі жолы үшін «Жоспардан алып тастау» түймесін пайдаланыңыз.'),
    'monthly_records': ('Строку нельзя удалить: есть связанная месячная задача №{task_id}. Используйте «Исключить из плана», чтобы сохранить связи.', 'Жолды жоюға болмайды: байланысқан №{task_id} айлық тапсырма бар. Байланыстарды сақтау үшін «Жоспардан алып тастау» түймесін пайдаланыңыз.'),
    'unknown': ('Операция не выполнена. Повторите действие, чтобы увидеть актуальную причину.', 'Әрекет орындалмады. Өзекті себебін көру үшін әрекетті қайталаңыз.'),
}
STATUSES = {'todo', 'in_progress', 'done', 'reviewed', 'not_executed'}


def format_notice(key, params=None, *, language='ru'):
    params = params or {}
    index = 1 if language == 'kk' else 0
    if key == 'task_blocked':
        reason_key = params.get('reason')
        if reason_key not in REASONS:
            return MESSAGES['unknown'][index]
        status = params.get('status') if params.get('status') in STATUSES else '—'
        reason = REASONS[reason_key][index].format(status=status)
        period = f"{int(params['year'])}-{int(params['month']):02d}"
        if index:
            return f"Жолды алып тастауға болмайды: №{int(params['task_id'])} тапсырма ({period}): {reason}. Тарих сақталды."
        return f"Строку нельзя исключить: задача №{int(params['task_id'])} ({period}): {reason}. История сохранена."
    return MESSAGES.get(key, MESSAGES['unknown'])[index].format(**params)


class AnnualRowConflict(HTTPException):
    def __init__(self, key, **params):
        self.notice_key = key
        self.notice_params = params
        super().__init__(409, format_notice(key, params, language=ui_locale.get()))


def notice_query(exc):
    key = getattr(exc, 'notice_key', 'unknown')
    params = getattr(exc, 'notice_params', {})
    return {'row_notice_key': key, **{'row_notice_' + k: str(v) for k, v in params.items()}}


def read_notice(request, user):
    """Never echo a language-bound error string from an old URL."""
    query = request.query_params
    key = query.get('row_notice_key')
    params = {}
    if key:
        params = {name: query.get('row_notice_' + name, '') for name in ('task_id','year','month','reason','status')}
    elif query.get('row_notice'):
        # Compatibility with the exact status message from stage328, RU or KK.
        raw = query['row_notice'][:2048]
        task = re.search(r'№\s*(\d+)', raw)
        period = re.search(r'\((\d{4})-(\d{1,2})\)', raw)
        status = re.search(r'(?:статус задачи|тапсырма мәртебесі)\s*[—-]\s*(todo|in_progress|done|reviewed|not_executed)\b', raw)
        key = 'unknown'
        if task and period and status:
            key = 'task_blocked'
            params = dict(task_id=task[1], year=period[1], month=period[2], reason='status', status=status[1])
    else:
        return None
    try:
        if key in ('task_blocked', 'monthly_records'):
            params['task_id'] = int(params['task_id'])
            if not 0 < params['task_id'] <= 2147483647:
                raise ValueError('Invalid task')
        if key == 'task_blocked':
            params['year'], params['month'] = int(params['year']), int(params['month'])
            if not 1 <= params['month'] <= 12 or not 1900 <= params['year'] <= 9999:
                raise ValueError('Invalid period')
        return format_notice(key, params, language=resolve_language(request, user))
    except (KeyError, TypeError, ValueError, OverflowError):
        return format_notice('unknown', language=resolve_language(request, user))
