"""Plain-text notification formatting; this module never sends messages."""
from app.core.i18n import normalize_language,translate
from app.core.i18n_messages import N_

NOTIFICATION_MESSAGES = (
    N_('Здравствуйте, {name}!'),
    N_('В системе School Monitor Вам назначены новые задачи.'),
    N_('🏫 Школа: {school}'),
    N_('📌 Как ответственному:'),
    N_('👥 Как соисполнителю:'),
    N_('  🕒 Срок выполнения: {deadline}'),
    N_('📊 Всего задач: {count}'),
    N_('🔗 Войти в School Monitor:'),
    N_('Если Вы впервые работаете в системе, сначала зарегистрируйтесь, затем войдите.'),
    N_('Сообщение подготовлено в School Monitor. Отправка выполняется вручную в WhatsApp.'),
)


def build_monthly_notification_message(*,recipient,platform_url,school_name=None,language='kk'):
    language = normalize_language(language) or 'kk'
    def text(message,**values):
        return translate(message,language).format(**values)
    lines = [text('Здравствуйте, {name}!',name=recipient.full_name),'',
             text('В системе School Monitor Вам назначены новые задачи.')]
    if school_name:
        lines.extend(['',text('🏫 Школа: {school}',school=school_name)])
    for tasks,heading in [(recipient.primary_tasks,'📌 Как ответственному:'),
                          (recipient.co_executor_tasks,'👥 Как соисполнителю:')]:
        if tasks:
            lines.extend(['',text(heading)])
            for task in tasks:
                lines.extend(['• '+task.title,text('  🕒 Срок выполнения: {deadline}',deadline=task.deadline_text)])
    lines.extend(['',text('📊 Всего задач: {count}',count=recipient.task_count),'',
                  text('🔗 Войти в School Monitor:'),platform_url.rstrip('/'),'',
                  text('Если Вы впервые работаете в системе, сначала зарегистрируйтесь, затем войдите.'),'',
                  text('Сообщение подготовлено в School Monitor. Отправка выполняется вручную в WhatsApp.')])
    return '\n'.join(lines)
