# app/modules/reports/enums.py
import enum


def enum_values(enum_cls):
    return [item.value for item in enum_cls]


# тип документа
class DocumentType(str, enum.Enum):
    PLAN = ("plan", "Жоспар")
    PROTOCOL = ("protocol", "Хаттама")
    ACT = ("act", "Акт")
    REPORT = ("report", "Есеп")
    REFERENCE = ("reference", "Анықтама")
    OTHER = ("other", "Басқа құжат")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class DocumentStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


# Тип отчета
class ReportType(str, enum.Enum):
    LESSON_OBSERVATION = ("lesson_observation", "Сабақты бақылау парағы")
    KNOWLEDGE_QUALITY_TABLE = ("knowledge_quality_table", "Білім сапасының кестесі")
    CHECKING_NOTEBOOKS_TABLE = ("checking_notebooks_table", "Дәптер тексеру кестесі")
    READING_SPEED_TABLE = ("Reading_speed_table", "Оқу жылдамдығы")
    DOCUMENT_ANALYSIS = ("document_analysis", "Құжаттарды талдау")
    ANALYTICAL_REFERENCE = ("analytical_reference", "Анықтама")
    CLASS_SUMMARY = ("class_summary", "Жалпылама талдау кестесі")
    TEACHER_ANALYSIS = ("teacher_analysis", "Мұғалім жұмысының талдауы")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


# статуса документа задачи
class TaskDocumentStatus(str, enum.Enum):
    DRAFT = ("draft", "Жоба (черновик)")
    UPLOADED = ("uploaded", "Жүктелді")
    SUBMITTED = ("submitted", "Қарауға жіберілді")
    APPROVED = ("approved", "Бекітілді")
    REJECTED = ("rejected", "Қабылданбады")
    ACCEPTED = ("accepted", "Қабылданды")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


# источник документа задачи
class TaskDocumentSource(str, enum.Enum):
    UPLOAD = ("upload", "Файл жүктеу")
    GENERATED = ("generated", "Жүйеде қалыптастырылған")
    TEMPLATE = ("template", "Шаблон негізінде")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj
