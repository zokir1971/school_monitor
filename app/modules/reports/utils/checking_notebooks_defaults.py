# app/modules/reports/utils/checking_notebooks_defaults.py

CHECKING_NOTEBOOKS_INFO_FIELDS = [
    {
        "key": "school_name",
        "label_ru": "Организация",
        "label_kz": "Білім беру ұйымы",
    },
    {
        "key": "checker_name",
        "label_ru": "Проверяющий",
        "label_kz": "Тексерушінің ТАӘ",
    },
    {
        "key": "checker_post",
        "label_ru": "Должность проверяющего",
        "label_kz": "Тексерушінің лауазымы",
    },
    {
        "key": "teacher_name",
        "label_ru": "Учитель",
        "label_kz": "Мұғалімнің ТАӘ",
    },
    {
        "key": "class_name",
        "label_ru": "Класс / группа",
        "label_kz": "Сынып / топ",
    },
    {
        "key": "subject_name",
        "label_ru": "Предмет",
        "label_kz": "Пән",
    },
    {
        "key": "check_date",
        "label_ru": "Дата проверки",
        "label_kz": "Тексеру күні",
    },
]


from copy import deepcopy
from app.modules.reports.rules.notebook_criteria import CHECKING_NOTEBOOKS_CRITERIA, CHECKING_NOTEBOOKS_RATING

CHECKING_NOTEBOOKS_DEFAULT_CRITERIA = deepcopy(CHECKING_NOTEBOOKS_CRITERIA)


def build_default_checking_notebooks_schema() -> dict:
    return deepcopy({
        'version': 3,
        'type': 'checking_notebooks_table',
        'info_fields': CHECKING_NOTEBOOKS_INFO_FIELDS,
        'criteria': CHECKING_NOTEBOOKS_DEFAULT_CRITERIA,
        'score_scale': [0, 1, 2],
        'rating': CHECKING_NOTEBOOKS_RATING,
    })
