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


CHECKING_NOTEBOOKS_DEFAULT_CRITERIA = [
    {
        "key": "exists",
        "label_ru": "Наличие тетради",
        "label_kz": "Дәптердің болуы",
        "scores": {
            "2": {
                "label_ru": "полностью выполняет",
                "label_kz": "толық орындайды",
            },
            "1": {
                "label_ru": "частично выполняет",
                "label_kz": "ішінара орындайды",
            },
            "0": {
                "label_ru": "не выполняет",
                "label_kz": "орындамайды",
            },
        },
    },
    {
        "key": "design",
        "label_ru": "Оформление тетради",
        "label_kz": "Дәптердің рәсімделуі",
        "scores": {
            "2": {
                "label_ru": "аккуратно, требования соблюдены",
                "label_kz": "ұқыпты, талаптар сақталған",
            },
            "1": {
                "label_ru": "есть отдельные нарушения",
                "label_kz": "жекелеген бұзушылықтар бар",
            },
            "0": {
                "label_ru": "требования не соблюдены",
                "label_kz": "талаптар сақталмаған",
            },
        },
    },
    {
        "key": "homework",
        "label_ru": "Выполнение домашнего задания",
        "label_kz": "Үй тапсырмасының орындалуы",
        "scores": {
            "2": {
                "label_ru": "выполняет полностью",
                "label_kz": "толық орындайды",
            },
            "1": {
                "label_ru": "выполняет частично",
                "label_kz": "ішінара орындайды",
            },
            "0": {
                "label_ru": "не выполняет",
                "label_kz": "орындамайды",
            },
        },
    },
    {
        "key": "literacy",
        "label_ru": "Грамотность",
        "label_kz": "Сауаттылық",
        "scores": {
            "2": {
                "label_ru": "без ошибок",
                "label_kz": "қатесіз",
            },
            "1": {
                "label_ru": "есть отдельные ошибки",
                "label_kz": "жекелеген қателер бар",
            },
            "0": {
                "label_ru": "много ошибок",
                "label_kz": "қателер көп",
            },
        },
    },
    {
        "key": "teacher_check",
        "label_ru": "Проверка учителем",
        "label_kz": "Мұғалімнің тексеруі",
        "scores": {
            "2": {
                "label_ru": "проверяется регулярно",
                "label_kz": "жүйелі түрде тексеріледі",
            },
            "1": {
                "label_ru": "проверяется нерегулярно",
                "label_kz": "жүйесіз тексеріледі",
            },
            "0": {
                "label_ru": "не проверяется",
                "label_kz": "тексерілмейді",
            },
        },
    },
    {
        "key": "correction",
        "label_ru": "Работа над ошибками",
        "label_kz": "Қатемен жұмыс",
        "scores": {
            "2": {
                "label_ru": "выполняется",
                "label_kz": "орындалады",
            },
            "1": {
                "label_ru": "выполняется частично",
                "label_kz": "ішінара орындалады",
            },
            "0": {
                "label_ru": "не выполняется",
                "label_kz": "орындалмайды",
            },
        },
    },
]


CHECKING_NOTEBOOKS_RATING = {
    "max_score_per_criterion": 2,
    "levels": [
        {
            "from": 90,
            "to": 100,
            "label_ru": "Высокий",
            "label_kz": "Жоғары",
        },
        {
            "from": 70,
            "to": 89,
            "label_ru": "Достаточный",
            "label_kz": "Жеткілікті",
        },
        {
            "from": 50,
            "to": 69,
            "label_ru": "Средний",
            "label_kz": "Орташа",
        },
        {
            "from": 0,
            "to": 49,
            "label_ru": "Низкий",
            "label_kz": "Төмен",
        },
    ],
}


def build_default_checking_notebooks_schema() -> dict:
    return {
        "type": "checking_notebooks_table",
        "info_fields": CHECKING_NOTEBOOKS_INFO_FIELDS,
        "criteria": CHECKING_NOTEBOOKS_DEFAULT_CRITERIA,
        "rating": CHECKING_NOTEBOOKS_RATING,
    }