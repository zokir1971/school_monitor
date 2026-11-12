"""Display-only localization for task completion and public QR verification."""
from app.core.i18n import translate
from app.core.i18n_messages import N_

COMPLETION_FEEDBACK_MESSAGES = (
    N_('Выберите файл для загрузки.'),
    N_('Выберите вариант завершения.'),
    N_('Выберите корректный вариант завершения.'),
    N_('Итоговый документ загружен. Задача завершена и отправлена на рассмотрение.'),
    N_('Задача завершена и отправлена на рассмотрение.'),
    N_('Неподдерживаемое действие.'),
    N_('Ошибка при работе с файлом.'),
    N_('Ошибка при сохранении данных.'),
    N_('Задача уже завершена.'),
    N_('Сначала загрузите итоговый документ.'),
    N_('Задача не найдена или недоступна.'),
    N_('Документ не найден или нет доступа'),
    N_('У документа отсутствует путь к файлу'),
    N_('Файл не найден в хранилище'),
)
BUILTIN_VERIFY_DETAIL_LABELS = (
    N_('Білім беру ұйымы'), N_('Педагог'), N_('Пән'),
    N_('Бақылаушы'), N_('Мұғалім'), N_('Сынып'),
)
VERIFY_REPORT_LABELS = {
    'lesson_observation': N_('Сабақты бақылау парағы'),
    'checking_notebooks': N_('Дәптер тексеру кестесі'),
}


def completion_message(value, language):
    if isinstance(value, str) and value in COMPLETION_FEEDBACK_MESSAGES:
        return translate(value, language)
    prefix = 'Не заполнены выбранные отчеты: '
    if isinstance(value, str) and value.startswith(prefix):
        from app.modules.reports.enums import ReportType
        labels = {entry.label_kz for entry in ReportType}
        # Translate known system labels only; preserve custom report names.
        names = [translate(name, language) if name in labels else name
                 for name in value[len(prefix):].split(', ')]
        return translate(N_('Не заполнены выбранные отчеты: {reports}'), language).format(reports=', '.join(names))
    return translate(N_('Не удалось завершить действие. Проверьте документ и выбранный вариант завершения.'), language)


def review_places_label(value, language):
    from app.modules.planning.enums import ReviewPlace
    labels = {entry.label_kz for entry in ReviewPlace}
    return ', '.join(translate(part, language) if part in labels else part
                     for part in (value or '—').split(', '))


def verification_message(value, language):
    known = {
        'QR-код недействителен': N_('QR-код недействителен'),
        'QR-код жарамсыз': N_('QR-код недействителен'),
        'QR-код немесе token жарамсыз.': N_('QR-код немесе token жарамсыз.'),
        'Signature has expired': N_('Срок действия ссылки проверки истёк.'),
        'Signature verification failed': N_('QR-код недействителен'),
        'Not enough segments': N_('QR-код недействителен'),
        'Тип отчета не указан': N_('Тип отчета не указан'),
        'Отчет не найден': N_('Отчет не найден'),
    }
    if isinstance(value, str) and value.startswith('Неизвестный тип отчета:'):
        source = N_('Неизвестный тип отчета.')
    else:
        source = known.get(value) if isinstance(value, str) else None
    return translate(source or N_('Не удалось проверить документ. Проверьте QR-код или ссылку.'), language)
