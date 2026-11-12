"""Superuser planning UI feedback; document contents and plan operations are unchanged."""
import re
from app.core.i18n import translate
from app.core.i18n_messages import N_
SUPER_PLANNING_ERRORS = (
    N_('Короткое название должно быть не короче 3 символов.'),
    N_('Загрузите файл .docx'),
    N_('В файле .docx должно быть минимум 2 таблицы: 1) объекты, 2) задачи.'),
)


def super_planning_feedback(value, language):
    if isinstance(value, str):
        match = re.fullmatch(r'Импорт завершён: объектов=(\d+), задач=(\d+)', value)
        if match:
            return translate(N_('Импорт завершён: объектов={objects}, задач={tasks}'), language).format(objects=match[1], tasks=match[2])
        if value.startswith('Ошибка импорта: '):
            detail = value[len('Ошибка импорта: '):]
            if detail in SUPER_PLANNING_ERRORS:
                return translate(detail, language)
            return translate(N_('Не удалось импортировать файл. Проверьте формат DOCX и наличие двух таблиц.'), language)
        if value in SUPER_PLANNING_ERRORS:
            return translate(value, language)
    return translate(N_('Не удалось выполнить действие. Проверьте шаблон и направление плана.'), language)
