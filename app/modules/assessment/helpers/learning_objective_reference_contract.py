"""Pure validation for the forthcoming reference importer, no database writes."""
from enum import Enum
import re


class LanguageSkill(str, Enum):
    LISTENING = 'listening'
    SPEAKING = 'speaking'
    READING = 'reading'
    WRITING = 'writing'
    LISTENING_SPEAKING = 'listening_speaking'
    LANGUAGE_NORMS = 'language_norms'
    LANGUAGE_SKILLS = 'language_skills'

    @property
    def label_kz(self):
        return {'listening': 'Тыңдалым', 'speaking': 'Айтылым', 'reading': 'Оқылым', 'writing': 'Жазылым',
                'listening_speaking': 'Тыңдалым және айтылым', 'language_skills': 'Тілдік дағдылар',
                'language_norms': 'Тілдік нормалардың қолданысы'}[self.value]

    @property
    def label_ru(self):
        return {'listening': 'Аудирование', 'speaking': 'Говорение', 'reading': 'Чтение', 'writing': 'Письмо',
                'listening_speaking': 'Аудирование и говорение', 'language_skills': 'Языковые навыки',
                'language_norms': 'Соблюдение языковых норм'}[self.value]


def normalize_quarters(values):
    if not isinstance(values, (list, tuple, set)) or not values:
        raise ValueError('At least one quarter must be explicitly supplied.')
    if any(type(value) is not int or not 1 <= value <= 4 for value in values):
        raise ValueError('Quarters must be integers from 1 to 4.')
    return tuple(sorted(set(values)))


def normalize_import_code(value, *, grade_level):
    """Normalize PDF spacing; only new imported standard codes are checked."""
    if type(grade_level) is not int or not 1 <= grade_level <= 12:
        raise ValueError('Grade must be 1–12.')
    if not isinstance(value, str):
        raise ValueError('Code must be text.')
    code = re.sub(r'\s+', '', value)
    if not re.fullmatch(r'(?:[1-9]|1[0-2])\.[0-9]+\.[0-9]+\.[0-9]+', code):
        raise ValueError('Expected a four-part learning objective code.')
    if int(code.split('.')[0]) != grade_level:
        raise ValueError('Objective code does not match grade.')
    return code


def normalize_skill(value):
    if value is None or value == '':
        return None
    return LanguageSkill(value).value
