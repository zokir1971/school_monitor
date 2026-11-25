"""School method association UI labels; stored codes and names are unchanged."""
from app.core.i18n import translate
from app.core.i18n_messages import N_

METHOD_ASSOCIATION_ERRORS = (
    N_('Не удалось определить школу текущего пользователя.'),
    N_('Передан недопустимый список методических объединений.'),
    N_('Не удалось выполнить операцию.'),
)


def association_name(value, language):
    from app.modules.schools.method_assoc import METHOD_ASSOCIATION_OPTIONS
    names = {option.name for option in METHOD_ASSOCIATION_OPTIONS}
    return translate(value, language) if value in names else value


def association_error(value, language):
    conflicts = {
        'Настройки изменились в другой вкладке. Показан текущий выбор. Проверьте его перед сохранением.':
            'Баптаулар басқа қойындыда өзгерді. Ағымдағы таңдау көрсетілді. Сақтамас бұрын оны тексеріңіз.',
        'Сохранённые методические объединения содержат конфликтующие записи. Обратитесь к администратору.':
            'Сақталған әдістемелік бірлестіктерде қайшы жазбалар бар. Әкімшіге хабарласыңыз.',
    }
    if isinstance(value, str) and value in conflicts:
        return conflicts[value] if language in ('kk', 'kz') else value
    source = value if isinstance(value, str) and value in METHOD_ASSOCIATION_ERRORS else 'Не удалось выполнить операцию.'
    return translate(source, language)

# Extraction markers for canonical names supplied dynamically by the service.
METHOD_ASSOCIATION_NAMES = (
    N_('Бастауыш сынып'),
    N_('Қазақ тілі мен әдебиеті'),
    N_('Орыс тілі мен әдебиеті'),
    N_('Өзбек тілі мен әдебиеті'),
    N_('Тәжік тілі мен әдебиеті'),
    N_('Шетел тілі'),
    N_('Математика'),
    N_('Информатика'),
    N_('Математика және информатика'),
    N_('Математика, информатика, физика'),
    N_('Физика және информатика'),
    N_('Химия және биология'),
    N_('Физика'),
    N_('Химия'),
    N_('Биология'),
    N_('География'),
    N_('Тарих'),
    N_('Тарих және география'),
    N_('АӘД және дене шынықтыру'),
    N_('Өнер және еңбек'),
    N_('Тіл пәндері'),
    N_('Жаратылыстану-математикалық'),
    N_('Қоғамдық-гуманитарлық'),
    N_('Сынып жетекшілерінің әдістемелік бірлестігі'),
)
