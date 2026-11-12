"""Display-only localization for the schools directory; school data stays unchanged."""
from app.core.i18n import translate
from app.core.i18n_messages import N_
SCHOOL_MESSAGES = (
    N_('Школа не найдена'),N_('Район не найден'),
    N_('Такая школа уже существует в этом районе'),N_('Файл не выбран'),
    N_('Разрешен только .xlsx файл'),N_('Файл пустой или не содержит данных'),
)

def school_feedback(value, language):
    if isinstance(value,str):
        if value in SCHOOL_MESSAGES:return translate(value,language)
        prefix='В Excel-файле нет колонки: '
        if value.startswith(prefix):
            # The exact imported column header is data and must remain unchanged.
            return translate(N_('В Excel-файле нет колонки: {column}'),language).format(column=value[len(prefix):])
    return translate(N_('Не удалось выполнить действие. Проверьте данные школы и выбранные фильтры.'),language)
