"""Read-only review results UI localization; authored content remains unchanged."""
import re
from app.core.i18n import translate
from app.core.i18n_messages import N_

REVIEW_RESULT_ERRORS = (
    N_('Для выбранного года месячные планы не найдены.'),
    N_('Для выбранного месяца план не найден.'),
    N_('Для пользователя не найден профиль сотрудника.'),
    N_('Для просмотра результатов необходимо выбрать место рассмотрения.'),
    N_('Для суперпользователя необходимо выбрать школу.'),
    N_('Документ не найден или у пользователя нет доступа.'),
    N_('Задача не найдена или у пользователя нет доступа.'),
    N_('Номер месяца должен находиться в диапазоне от 1 до 12.'),
    N_('Передан некорректный фильтр результатов.'),
    N_('Передана неизвестная инстанция рассмотрения.'),
    N_('Результат рассмотрения не найден или у пользователя нет доступа.'),
    N_('У выбранной школы отсутствует активный годовой план.'),
    N_('У документа отсутствует путь к файлу.'),
    N_('У документа отсутствует файл.'),
    N_('У пользователя не определена школа.'),
    N_('У пользователя нет доступа к результатам рассмотрения.'),
    N_('Файл документа не найден в хранилище.'),
)


def result_message(value, language):
    source = value if isinstance(value, str) and value in REVIEW_RESULT_ERRORS else N_('Не удалось получить результаты рассмотрения. Проверьте выбранные фильтры и доступ к задаче.')
    return translate(source, language)


def result_label(value, language):
    from app.modules.planning.enums import PlanItemStatus, ReviewPlace, AssignmentKind
    labels = {entry.label_kz for enum in (PlanItemStatus, ReviewPlace, AssignmentKind) for entry in enum}
    labels.add(N_('Жауапты'))
    # Labels may combine participation roles; free-form names are never passed here.
    from app.modules.planning.review_places import label_for_message
    return ', '.join(label_for_message(part, language) or (translate(part, language) if part in labels else part)
                     for part in (value or '—').split(', '))


def protocol_label(value, language):
    # The service builds "Протокол [№number] [от dd.mm.yyyy]".
    # Preserve the authored protocol number, including spaces and punctuation.
    if not isinstance(value, str):
        return value
    match = re.fullmatch(r'Протокол(?: №(.*?))?(?: от (\d{2}\.\d{2}\.\d{4}))?', value)
    if not match:
        return value
    number, date = match.groups()
    parts = [translate(N_('Протокол'), language)]
    if number is not None:
        parts.append('№' + number)
    if date:
        parts.append(translate(N_('от'), language) + ' ' + date)
    return ' '.join(parts)
