"""Subject availability from the supplied curriculum; no database dependencies."""

LANGUAGES = ('kz', 'ru', 'uz', 'ug', 'tg')


def allowed_role(role: str, language: str, grade: int) -> bool:
    if language not in LANGUAGES or not 1 <= grade <= 11:
        return False
    if role == 'kz_language':
        return grade >= 2 if language == 'kz' else grade <= 4
    if role == 'kz_literature':
        return language == 'kz' and grade >= 5
    if role == 'kz_combined':
        return language != 'kz' and grade >= 5
    if role == 'ru_language':
        return grade >= 2 if language == 'ru' else 2 <= grade <= 4
    if role == 'ru_literature':
        return language == 'ru' and grade >= 5
    if role == 'ru_combined':
        return language != 'ru' and grade >= 5
    if role == 'english':
        return grade >= 3
    if role == 'native_language':
        return language in ('uz', 'ug', 'tg') and grade >= 2
    if role == 'native_literature':
        return language in ('uz', 'ug', 'tg') and grade >= 5
    if role == 'literary_reading':
        return 2 <= grade <= 4
    if role == 'literacy':
        return grade == 1
    return canonical_role(role) == 'general'


def validate_rule(language, grade_from, grade_to, role, threshold):
    if not 1 <= grade_from <= grade_to <= 11:
        raise ValueError('Допустимый диапазон классов: 1–11.')
    invalid = [str(g) for g in range(grade_from, grade_to + 1)
               if not allowed_role(role, language, g)]
    if invalid:
        raise ValueError('Предмет не предусмотрен для выбранного языка обучения в классах: '
                         + ', '.join(invalid) + '. Разделите диапазон по учебному плану.')
    if threshold is not None and (type(threshold) is not int or threshold < 2):
        raise ValueError('Порог деления должен быть целым числом не меньше 2.')
    native = ((role == 'kz_language' and language == 'kz')
              or (role == 'ru_language' and language == 'ru')
              or role in ('kz_literature', 'ru_literature', 'native_language',
                          'native_literature', 'literary_reading', 'literacy'))
    if native and threshold is not None:
        raise ValueError('Для языка обучения, литературы и обучения грамоте используйте режим «Весь класс».')


LANGUAGE_GROUP = 'uz_ug_tg'

ALL_LANGUAGES = 'all'


def supports_all_languages(role, category_code):
    return canonical_role(role) == 'general' and category_code != 'language_literature'


def expand_languages(language, *, allow_all=False):
    if language == ALL_LANGUAGES:
        if not allow_all:
            raise ValueError('Для языкового предмета выберите конкретный язык обучения '
                             'или группу «Узбекский / уйгурский / таджикский».')
        return LANGUAGES
    if language == LANGUAGE_GROUP:
        return 'uz', 'ug', 'tg'
    if language in LANGUAGES:
        return language,
    raise ValueError('Выберите язык обучения.')


# These are teaching restrictions, not the catalogue of subjects or categories.
POLICIES = {
    'general': 'Без специальных языковых ограничений',
    'literacy': 'Обучение грамоте / Азбука (1 класс)',
    'literary_reading': 'Литературное чтение (2–4 классы)',
    'native_language': 'Узбекский / уйгурский / таджикский язык',
    'native_literature': 'Узбекская / уйгурская / таджикская литература',
    'kz_language': 'Казахский язык',
    'kz_literature': 'Казахская литература',
    'kz_combined': 'Казахский язык и литература',
    'ru_language': 'Русский язык',
    'ru_literature': 'Русская литература',
    'ru_combined': 'Русский язык и литература',
    'english': 'Иностранный язык (с 3 класса)',
}
LEGACY_GENERAL_ROLES = {
    'mathematics', 'informatics', 'natural_science', 'physics',
    'chemistry', 'biology', 'geography',
}


def canonical_role(role):
    return 'general' if role in LEGACY_GENERAL_ROLES else role
