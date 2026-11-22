# app/modules/planning/enums.py

import enum


class ResponsibleRole(str, enum.Enum):
    DIRECTOR = ('director', 'Директор', 'Директор', 'Директор', 'Директор')
    D_OTIJO = ('d_otijo', 'ДОТІЖО', 'Директордың оқу-тәрбие ісі жөніндегі орынбасары', 'ЗДУВР', 'Заместитель директора по учебно-воспитательной работе')
    D_OIJO = ('d_oijo', 'ДОІЖО', 'Директордың оқу ісі жөніндегі орынбасары', 'ЗДУР', 'Заместитель директора по учебной работе')
    D_TIJO = ('d_tijo', 'ДТІЖО', 'Директордың тәрбие ісі жөніндегі орынбасары', 'ЗДВР', 'Заместитель директора по воспитательной работе')
    D_OAJO = ('d_oajo', 'ДОӘІЖО', 'Директордың оқу-әдістемелік ісі жөніндегі орынбасары', 'ЗДУМР', 'Заместитель директора по учебно-методической работе')
    D_BOZHO = ('d_bozho', 'ДБОЖО', 'Директордың бейіндік оқыту жөніндегі орынбасары', 'ЗДПО', 'Заместитель директора по профильному обучению')
    D_SHIZHO = ('d_shizho', 'ДШІЖО', 'Директордың шаруашылық ісі жөніндегі орынбасары', 'ЗДХР', 'Заместитель директора по хозяйственной работе')
    INTERNAT_HEAD = ('internat_head', 'ИМ', 'Интернат меңгерушісі', 'ЗИ', 'Заведующий интернатом')
    D_INFORMATIZATION = ('d_informatization', 'ДАЖО', 'Директордың ақпараттандыру жөніндегі орынбасары', 'ЗДИ', 'Заместитель директора по информатизации')
    D_FOREIGN_LANGUAGE = ('d_foreign_language', 'ДШТЖО', 'Директордың шет тілі жөніндегі орынбасары', 'ЗДИЯ', 'Заместитель директора по иностранному языку')
    D_PRIMARY_CLASSES = ('d_primary_classes', 'ДБСЖО', 'Директордың бастауыш сыныптар жөніндегі орынбасары', 'ЗДНК', 'Заместитель директора по начальным классам')
    AED_TO = ('aed_to', 'АӘД және ТО', 'Алғашқы әскери және технологиялық дайындықтың педагог-ұйымдастырушысы', 'ПОНВТП', 'Педагог-организатор начальной военной и технологической подготовки')
    PU = ('pu', 'Педагог ұйымдастырушы', 'Педагог ұйымдастырушы', 'ПО', 'Педагог-организатор')
    QBBP = ('qbbp', 'ҚББП', 'Қосымша білім беру педагогі', 'ПДО', 'Педагог дополнительного образования')
    PKBB = ('pkbb', 'ПКББ', 'Педагог-кәсіби бағдар беруші', 'ПП', 'Педагог-профориентатор')
    ABJ = ('abj', 'ӘБЖ', 'Әдістемелік бірлестік жетекшісі', 'РМО', 'Руководитель методического объединения')
    AP = ('ap', 'Әлеуметтік педагог', 'Әлеуметтік педагог', 'СП', 'Социальный педагог')
    SJ = ('sj', 'Сынып жетекшісі', 'Сынып жетекшісі', 'КР', 'Классный руководитель')
    UJ = ('uj', 'Үйірме жетекшісі', 'Үйірме жетекшісі', 'РК', 'Руководитель кружка')
    PED_PSY = ('ped_psy', 'Педагог-психолог', 'Педагог-психолог', 'ППс', 'Педагог-психолог')
    DEFECTOLOGIST = ('defectologist', 'Дефектолог', 'Дефектолог', 'Дефектолог', 'Дефектолог')
    LIBRARIAN = ('librarian', 'Кітапханашы', 'Кітапханашы', 'Библиотекарь', 'Библиотекарь')
    SCH_NURS = ('sch_nurs', 'Мектеп медбикесі', 'Мектеп медбикесі', 'Медсестра', 'Школьная медсестра')
    GUIDE = ('guide', 'Аға тәлімгер', 'Аға тәлімгер', 'СВ', 'Старший вожатый')

    def __new__(cls, value: str, label_kz: str, full_kz: str, short_ru: str, full_ru: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        # Existing compact labels and all persisted values stay compatible.
        obj.label_kz = label_kz
        obj.full_kz = full_kz
        obj.short_ru = short_ru
        obj.full_ru = full_ru
        return obj

    def option_label(self, language: str = "kk") -> str:
        short, full = (self.short_ru, self.full_ru) if language == "ru" else (self.label_kz, self.full_kz)
        return f'{short} — «{full}»'


class AssignmentKind(str, enum.Enum):
    PRIMARY = ("primary", "Негізгі орындаушы")
    CO_EXECUTOR = ("co_executor", "Қосалқы орындаушы")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class MonthPlanNotificationStatus(str, enum.Enum):
    """
    Состояние уведомления исполнителя.

    Жизненный цикл:

        PENDING
            ↓
        SENT
            ↓
        ACCEPTED
    """

    # Уведомление ещё не отправлено.
    PENDING = ("pending", "Жіберілмен")

    # Администратор отправил уведомление исполнителю.
    SENT = ("sent", "Жіберілді")

    # Исполнитель принял задачу к исполнению.
    ACCEPTED = ("accepted", "Орындауға қабылданды")

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
    REVIEWED = ("reviewed", "Қаралды")
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
