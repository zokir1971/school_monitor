# app/modules/planning/enums.py

import enum


class ResponsibleRole(str, enum.Enum):
    DIRECTOR = ("director", "Директор")
    D_OTIJO = ("d_otijo", "ДОТІЖО")
    D_OIJO = ("d_oijo", "ДОІЖО")
    D_TIJO = ("d_tijo", "ДТІЖО")
    D_OAJO = ("d_oajo", "ДОӘІЖО")
    D_BOZHO = ("d_bozho", "ДБОЖО")
    D_SHIZHO = ("d_shizho", "ДШІЖО")
    AED_TO = ("aed_to", "АӘД және ТО")
    PU = ("pu", "Педагог ұйымдастырушы")
    QBBP = ("qbbp", "ҚББП")
    PKBB = ("pkbb", "ПКББ")
    ABJ = ("abj", "ӘБЖ")
    AP = ("ap", "Әлеуметтік педагог")
    SJ = ("sj", "Сынып жетекшісі")
    UJ = ("uj", "Үйірме жетекшісі")
    PED_PSY = ("ped_psy", "Педагог-психолог")
    DEFECTOLOGIST = ("defectologist", "Дефектолог")
    LIBRARIAN = ("librarian", "Кітапханашы")
    SCH_NURS = ("sch_nurs", "Мектеп медбикесі")
    GUIDE = ("guide", "Аға тәлімгер")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class AssignmentKind(str, enum.Enum):
    PRIMARY = ("primary", "Негізгі орындаушы")
    CO_EXECUTOR = ("co_executor", "Қосалқы орындаушы")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class PlanPeriodType(str, enum.Enum):
    MONTH = ("month", "Бір ай")
    MONTHS = ("months", "Бірнеше ай")
    MONTHLY = ("monthly", "Ай сайын")
    QUARTER = ("quarter", "Тоқсан сайын")
    ALL_YEAR = ("all_year", "Жыл бойы")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class PlanStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class PlanItemStatus(str, enum.Enum):
    TODO = ("todo", "Жоспарланған")
    IN_PROGRESS = ("in_progress", "Орындалу үстінде")
    DONE = ("done", "Орындалды")
    NOT_EXECUTED = ("not_executed", "Орындалмады")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


# Форма контроля
class ControlForm(str, enum.Enum):
    PERSONAL = ("personal", "Жеке бақылау")
    CLASS_GENERALIZING = ("class_generalizing", "Сыныптық-жалпылау бақылауы")
    SUBJECT_GENERALIZING = ("subject_generalizing", "Пәндік-жалпылау бақылауы")
    THEMATIC_GENERALIZING = ("thematic_generalizing", "Тақырыптық-жалпылау бақылауы")
    OVERVIEW = ("overview", "Шолу бақылауы")
    COMPLEX_GENERALIZING = ("complex_generalizing", "Кешенді-жалпылау бақылауы")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


# Вид контроля
class ControlKind(str, enum.Enum):
    FRONT = ("front", "Фронталды бақылау")
    THEMATIC = ("thematic", "Тақырыптық бақылау")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


# Объект контроля
class ControlScope(str, enum.Enum):
    CLASS = ("class", "Сынып")
    PARALLEL = ("parallel", "Параллель")
    SUBJECT = ("subject", "Пән")
    TEACHER = ("teacher", "Мұғалім")
    DOCUMENTATION = ("documentation", "Құжаттар")
    COMPLEX = ("complex", "Кешенді")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class ReviewPlace(str, enum.Enum):
    PED_COUNCIL = ("ped_council", "Пед.кеңес")
    METHOD_COUNCIL = ("method_council", "Әд.кеңес")
    DIRECTOR_COUNCIL = ("director_council", "ДЖ.кеңес")
    ADMINISTRATIVE_COUNCIL = ("administrative_council", "Әк.кеңес")
    METHOD_ASSOC = ("method_assoc", "ӘБ.отырысы")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj
