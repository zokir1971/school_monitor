# app/modules/assessment/enums.py

from __future__ import annotations

import enum


class AssessmentStatus(str, enum.Enum):
    """
    Жизненный цикл оценочной/диагностической работы.
    """

    DRAFT = ("draft", "Жоба")
    READY = ("ready", "Дайын")
    ACTIVE = ("active", "Белсенді")
    COMPLETED = ("completed", "Аяқталды")
    ARCHIVED = ("archived", "Мұрағат")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class AssessmentInputMode(str, enum.Enum):
    """
    Способ получения результатов.
    """

    MANUAL = ("manual", "Қолмен енгізу")
    ONLINE = ("online", "Онлайн орындау")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class AssessmentType(str, enum.Enum):
    """
    Назначение оценочной работы.

    CUSTOM позволяет не менять схему БД,
    если появляется новый организационный тип работы.
    """

    BASELINE = ("baseline", "Нөлдік бақылау")
    DIAGNOSTIC = ("diagnostic", "Диагностикалық жұмыс")
    MONITORING = ("monitoring", "Мониторингтік жұмыс")
    CONTROL = ("control", "Бақылау жұмысы")
    SUMMATIVE = ("summative", "Жиынтық бағалау")
    CUSTOM = ("custom", "Басқа")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class AssessmentParticipationStatus(str, enum.Enum):
    """
    Состояние участия учащегося в конкретной работе.
    """

    ASSIGNED = ("assigned", "Тағайындалды")
    IN_PROGRESS = ("in_progress", "Орындалуда")

    SUBMITTED = ("submitted", "Тексеруге жіберілді")

    COMPLETED = ("completed", "Орындалды")

    ABSENT = ("absent", "Қатыспады")
    EXCUSED = ("excused", "Босатылды")
    NOT_COMPLETED = ("not_completed", "Орындамады")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class AssessmentGrade(str, enum.Enum):
    """
    Итоговая школьная оценка.

    Значение enum является строкой специально:
    так удобнее использовать его в PostgreSQL,
    DTO, API и шаблонах.
    """

    EXCELLENT = ("5", "Үздік")
    GOOD = ("4", "Жақсы")
    SATISFACTORY = ("3", "Қанағаттанарлық")
    UNSATISFACTORY = ("2", "Қанағаттанарлықсыз")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class AssessmentQuestionType(str, enum.Enum):
    """
    Тип задания.

    Сейчас enum уже предусматривает основные возможности
    старого проекта, даже если онлайн-режим реализуем позже.
    """

    SINGLE_CHOICE = ("single_choice", "Бір дұрыс жауап")
    MULTIPLE_CHOICE = ("multiple_choice", "Бірнеше дұрыс жауап")

    TRUE_FALSE = ("true_false", "Дұрыс / бұрыс")

    SHORT_TEXT = ("short_text", "Қысқа жауап")
    NUMBER = ("number", "Сандық жауап")

    MATCHING = ("matching", "Сәйкестендіру")
    ORDERING = ("ordering", "Ретін анықтау")
    FILL_GAPS = ("fill_gaps", "Бос орындарды толтыру")

    FORMULA = ("formula", "Формула енгізу")
    IMAGE_CHOICE = ("image_choice", "Сурет бойынша таңдау")

    MANUAL_REVIEW = ("manual_review", "Қолмен тексеру")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class AssessmentAnswerStatus(str, enum.Enum):
    """
    Состояние проверки ответа ученика.
    """

    NOT_ANSWERED = ("not_answered", "Жауап берілмеді")
    PENDING_REVIEW = ("pending_review", "Тексеруді күтуде")
    CHECKED = ("checked", "Тексерілді")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class AssessmentTaskLinkType(str, enum.Enum):
    """
    Роль Assessment относительно задачи ВШК.

    Оставляем возможность в будущем использовать одну работу
    как основной источник или как дополнительный материал.
    """

    PRIMARY = ("primary", "Негізгі дереккөз")
    ADDITIONAL = ("additional", "Қосымша дереккөз")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class AssessmentMode(str, enum.Enum):
    """
    Структурный режим Assessment.

    WITHOUT_OBJECTIVES:
        - диагностические / нөлдік бақылау;
        - учебные цели не используются;
        - может входить в многопредметную campaign.

    ASSESSMENT_BY_SECTION:
        - БЖБ / СОР;
        - учебные цели обязательны.

    ASSESSMENT_BY_QUARTER:
        - ТЖБ / СОЧ;
        - учебные цели обязательны.
    """

    BY_OBJECTIVES = ("by_objectives", "Оқу мақсаттары бойынша")
    WITHOUT_OBJECTIVES = ("without_objectives", "Диагностикалық бақылау")
    ASSESSMENT_BY_SECTION = ("assessment_by_section", "БЖБ / СОР")
    ASSESSMENT_BY_QUARTER = ("assessment_by_quarter", "ТЖБ / СОЧ")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class AssessmentCheckpoint(str, enum.Enum):
    """
    Контрольная точка Assessment
    для анализа динамики качества знаний
    внутри учебного года.

    Нөлдік бақылау является отправной точкой.

    Не каждый Assessment обязан иметь checkpoint.
    Обычные Assessment не участвуют в годовой динамике.

    BASELINE:
        - нөлдік бақылау;
        - стартовая точка учебного года.

    QUARTER_1 ... QUARTER_4:
        - официальная контрольная точка
          соответствующей четверти.

    FINAL:
        - отдельная итоговая годовая контрольная точка,
          если школа её использует.
    """

    BASELINE = ("baseline", "Нөлдік бақылау")

    QUARTER_1 = ("quarter_1", "I тоқсан")
    QUARTER_2 = ("quarter_2", "II тоқсан")
    QUARTER_3 = ("quarter_3", "III тоқсан")
    QUARTER_4 = ("quarter_4", "IV тоқсан")

    FINAL = ("final", "Жылдық қорытынды")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class AssessmentBlueprintStatus(str, enum.Enum):
    """
    Жизненный цикл спецификации Assessment.

    DRAFT:
        - спецификация редактируется;
        - состав целей, типов заданий и параметров
          ещё может быть неполным.

    READY:
        - спецификация прошла валидацию;
        - может использоваться для создания Assessment,
          подбора заданий из банка или AI-генерации.

    ARCHIVED:
        - спецификация больше не используется
          для создания новых Assessment;
        - сохраняется для истории.
    """

    DRAFT = ("draft", "Жоба")
    READY = ("ready", "Дайын")
    ARCHIVED = ("archived", "Мұрағат")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class AssessmentLanguage(str, enum.Enum):
    """
    Язык содержания Assessment и заданий.

    Язык хранится явно, поскольку одна и та же
    спецификация предмета и класса может существовать
    на разных языках обучения.
    """

    KAZAKH = ("kk", "Қазақ тілі")
    RUSSIAN = ("ru", "Орыс тілі")
    ENGLISH = ("en", "Ағылшын тілі")

    def __new__(cls, value: str, label_kz: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class AssessmentQuestionDifficulty(str, enum.Enum):
    """
    Уровень сложности задания банка вопросов.
    """

    BASIC = ("basic", "Базалық")
    MEDIUM = ("medium", "Орта")
    ADVANCED = ("advanced", "Жоғары")

    def __new__(
            cls,
            value: str,
            label_kz: str,
    ):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class QuestionBankItemOrigin(str, enum.Enum):
    """
    Происхождение задания банка вопросов.
    """

    MANUAL = ("manual", "Қолмен жасалған")
    AI_GENERATED = (
        "ai_generated",
        "AI арқылы жасалған",
    )
    IMPORTED = ("imported", "Импортталған")

    def __new__(
            cls,
            value: str,
            label_kz: str,
    ):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class QuestionBankItemStatus(str, enum.Enum):
    """
    Жизненный цикл задания банка вопросов.
    """

    DRAFT = ("draft", "Жоба")
    REVIEW = ("review", "Тексеруде")
    READY = ("ready", "Дайын")
    REJECTED = ("rejected", "Қабылданбады")
    ARCHIVED = ("archived", "Мұрағат")

    def __new__(
            cls,
            value: str,
            label_kz: str,
    ):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class AIQuestionGenerationRunStatus(str, enum.Enum):
    """
    Состояние одного запуска AI-генерации вопросов.
    """
    RUNNING = ("running", "Генерация орындалуда")
    COMPLETED = ("completed", "Генерация аяқталды")
    FAILED = ("failed", "Генерация қатемен аяқталды")

    def __new__(
            cls,
            value: str,
            label_kz: str,
    ):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class AIQuestionQualityVerdict(str, enum.Enum):
    PASS = ("pass", "Сапасы жеткілікті")
    NEEDS_REVIEW = (
        "needs_review",
        "Қосымша тексеру қажет",
    )
    REJECT = (
        "reject",
        "Қабылдамау ұсынылады",
    )

    def __new__(
            cls,
            value: str,
            label_kz: str,
    ):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class AIQuestionQualityIssueSeverity(str, enum.Enum):
    WARNING = ("warning", "Ескерту")
    ERROR = ("error", "Маңызды мәселе")

    def __new__(
            cls,
            value: str,
            label_kz: str,
    ):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj


class QuestionBankReviewDecision(str, enum.Enum):
    """
    Решение человека по результатам
    экспертной проверки задания банка вопросов.

    Не является QuestionBankItemStatus.

    APPROVED: REVIEW -> READY

    REJECTED: REVIEW -> REJECTED
    """
    APPROVED = ("approved", "Мақұлданды")
    REJECTED = ("rejected", "Қабылданбады")

    def __new__(
            cls,
            value: str,
            label_kz: str,
    ):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label_kz = label_kz
        return obj
