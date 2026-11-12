# app/modules/assessment/schemas/teacher_question_bank_dto.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.modules.assessment.enums import (
    AssessmentLanguage,
    AssessmentQuestionDifficulty,
    AssessmentQuestionType,
    QuestionBankItemOrigin,
    QuestionBankItemStatus,
    QuestionBankReviewDecision,
)


# =========================================================
# LIST ITEM
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankItemDTO:
    """
    Одна строка списка Question Bank учителя.
    """

    item_id: int

    subject_id: int
    subject_name: str

    grade_level: int

    question_type: AssessmentQuestionType
    difficulty: AssessmentQuestionDifficulty
    language: AssessmentLanguage

    status: QuestionBankItemStatus
    origin: QuestionBankItemOrigin

    title: str | None
    text: str

    objective_count: int

    created_at: datetime
    updated_at: datetime


# =========================================================
# DETAIL — LEARNING OBJECTIVE
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankObjectiveDTO:
    """
    Учебная цель задания Question Bank.

    quarter принадлежит LearningObjective
    и является источником учебной четверти задания.
    """

    learning_objective_id: int

    quarter: int

    code: str
    title_kz: str
    title_ru: str | None

    order_no: int

# =========================================================
# DETAIL — HUMAN REVIEW
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankReviewDTO:
    """
    Историческая запись Human Review.
    """

    review_id: int

    reviewer_user_id: int | None
    reviewer_name: str | None

    decision: QuestionBankReviewDecision

    comment: str | None

    created_at: datetime


# =========================================================
# DETAIL
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankDetailDTO:
    """
    Полная карточка собственного задания учителя.
    """

    item_id: int

    subject_id: int
    subject_name: str

    grade_level: int
    quarter: int

    question_type: AssessmentQuestionType
    difficulty: AssessmentQuestionDifficulty
    language: AssessmentLanguage

    status: QuestionBankItemStatus
    origin: QuestionBankItemOrigin

    title: str | None

    text: str
    text_segments: list[dict[str, Any]]

    instruction: str | None

    content: dict
    answer_key: dict
    grading_settings: dict

    max_score: Decimal

    explanation: str | None
    author_comment: str | None

    created_at: datetime
    updated_at: datetime

    objectives: list[
        TeacherQuestionBankObjectiveDTO
    ]

    reviews: list[
        TeacherQuestionBankReviewDTO
    ]

# =========================================================
# COUNTERS
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankCountersDTO:
    """
    Счётчики собственных заданий учителя.
    """

    total: int = 0

    draft: int = 0
    review: int = 0
    ready: int = 0
    rejected: int = 0
    archived: int = 0


# =========================================================
# PAGE
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankPageDTO:
    """
    Данные страницы Question Bank учителя.
    """

    items: list[TeacherQuestionBankItemDTO]

    counters: TeacherQuestionBankCountersDTO

    selected_status: QuestionBankItemStatus | None


# =========================================================
# CREATE — TEACHING SCOPE
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankTeachingScopeDTO:
    """
    Разрешённая комбинация предмет + класс
    для текущего учителя.
    """

    subject_id: int
    subject_code: str

    subject_name_kz: str
    subject_name_ru: str | None

    grade_level: int


# =========================================================
# CREATE — LEARNING OBJECTIVE
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankLearningObjectiveDTO:
    """
    Учебная цель выбранного предмета,
    класса и четверти.
    """

    learning_objective_id: int

    quarter: int

    code: str

    title_kz: str
    title_ru: str | None
    title_segments_kz: tuple[dict[str, str], ...] = ()
    title_segments_ru: tuple[dict[str, str], ...] = ()

# =========================================================
# CREATE CONTEXT
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankCreateContextDTO:
    """
    Контекст страницы создания QuestionBankItem.

    teaching_scope определяет разрешённые
    комбинации предмет + класс текущего учителя.
    """

    teaching_scope: list[
        TeacherQuestionBankTeachingScopeDTO
    ]

# =========================================================
# CREATE DRAFT — COMMAND
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankCreateDraftDTO:
    """
    Команда создания черновика задания учителем.

    Все значения должны быть повторно проверены
    Service Layer. Данным формы доверять нельзя.
    """

    subject_id: int
    grade_level: int
    quarter: int

    objective_id: int

    question_type: AssessmentQuestionType
    difficulty: AssessmentQuestionDifficulty
    language: AssessmentLanguage

    title: str | None

    text: str
    text_segments: list[dict[str, Any]]

    instruction: str | None

    content: dict[str, Any]
    answer_key: dict[str, Any]
    grading_settings: dict[str, Any]

    max_score: Decimal

    explanation: str | None
    author_comment: str | None


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankCreatedDraftDTO:
    item_id: int
    status: QuestionBankItemStatus


# =========================================================
# EDIT — CONTEXT
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankEditContextDTO:
    """
    Контекст страницы редактирования собственного задания.

    Редактирование разрешается для:
        - DRAFT;
        - REJECTED.

    teaching_scope используется для проверки и отображения
    разрешённых текущему учителю комбинаций предмет + класс.

    learning_objectives содержит учебные цели текущего
    предмета, класса и четверти редактируемого задания.
    """

    item: TeacherQuestionBankDetailDTO

    teaching_scope: list[
        TeacherQuestionBankTeachingScopeDTO
    ]

    learning_objectives: list[
        TeacherQuestionBankLearningObjectiveDTO
    ]

# =========================================================
# UPDATE DRAFT — COMMAND
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankUpdateDraftDTO:
    """
    Команда обновления собственного задания учителя.

    Service Layer обязан повторно проверить:
        - авторство задания;
        - допустимость статуса DRAFT / REJECTED;
        - teaching scope;
        - LearningObjective;
        - Question Contract.

    После успешного сохранения:
        DRAFT    -> DRAFT
        REJECTED -> DRAFT

    Данным web-формы доверять нельзя.
    """
    subject_id: int
    grade_level: int
    quarter: int

    objective_id: int

    question_type: AssessmentQuestionType
    difficulty: AssessmentQuestionDifficulty
    language: AssessmentLanguage

    title: str | None

    text: str
    text_segments: list[dict[str, Any]]

    instruction: str | None

    content: dict[str, Any]
    answer_key: dict[str, Any]
    grading_settings: dict[str, Any]

    max_score: Decimal

    explanation: str | None
    author_comment: str | None


# =========================================================
# QUESTION BANK CATALOG — FILTER
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankCatalogFilterDTO:
    """
    Текущий фильтр общего каталога Question Bank.

    subject_id + grade_level определяют
    учебный контекст.

    objective_id ограничивает список заданий
    выбранной учебной целью.
    """

    subject_id: int | None = None
    grade_level: int | None = None
    quarter: int | None = None
    objective_id: int | None = None


# =========================================================
# QUESTION BANK CATALOG — ITEM
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankCatalogItemDTO:
    """
    Задание общего Question Bank.

    Авторство задания не ограничивает его просмотр.
    is_own используется только для определения
    доступных действий над заданием.
    """

    item_id: int

    subject_id: int
    subject_name: str

    grade_level: int
    quarter: int

    objectives: list[
        TeacherQuestionBankObjectiveDTO
    ]

    question_type: AssessmentQuestionType
    difficulty: AssessmentQuestionDifficulty
    language: AssessmentLanguage

    status: QuestionBankItemStatus
    origin: QuestionBankItemOrigin

    title: str | None

    text: str
    text_segments: list[dict[str, Any]]

    instruction: str | None

    content: dict[str, Any]
    answer_key: dict[str, Any]
    grading_settings: dict[str, Any]
    explanation: str | None

    max_score: Decimal

    created_by_user_id: int | None
    author_name: str | None

    is_own: bool

    created_at: datetime
    updated_at: datetime

    available_languages: tuple[str, ...] = ()


# =========================================================
# QUESTION BANK CATALOG — PAGE
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankCatalogPageDTO:
    """
    Данные страницы общего каталога Question Bank.

    teaching_scope:
        доступные текущему учителю предметы
        и параллели.

    learning_objectives:
        учебные цели выбранного предмета
        и параллели.

    items:
        задания общего банка по выбранному фильтру.
    """

    teaching_scope: list[
        TeacherQuestionBankTeachingScopeDTO
    ]

    learning_objectives: list[
        TeacherQuestionBankLearningObjectiveDTO
    ]

    filters: TeacherQuestionBankCatalogFilterDTO

    items: list[
        TeacherQuestionBankCatalogItemDTO
    ]

    offset: int = 0
    has_next: bool = False

# =========================================================
# HUMAN REVIEW — ITEM
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionReviewItemDTO:
    """
    Задание, доступное текущему учителю
    для Human Review.

    Эксперт получает полный педагогический контекст:
        - предмет;
        - класс;
        - четверть;
        - учебные цели;
        - параметры задания;
        - содержимое;
        - эталонный ответ.

    В очередь не должны попадать
    собственные задания пользователя.
    """

    item_id: int

    subject_id: int
    subject_name: str

    grade_level: int
    quarter: int

    objectives: list[
        TeacherQuestionBankObjectiveDTO
    ]

    question_type: AssessmentQuestionType
    difficulty: AssessmentQuestionDifficulty
    language: AssessmentLanguage

    status: QuestionBankItemStatus
    origin: QuestionBankItemOrigin

    title: str | None

    text: str
    text_segments: list[dict[str, Any]]

    instruction: str | None

    content: dict[str, Any]
    answer_key: dict[str, Any]
    grading_settings: dict[str, Any]

    max_score: Decimal

    created_by_user_id: int | None
    author_name: str | None

    created_at: datetime
    updated_at: datetime
    explanation: str | None = None

# =========================================================
# HUMAN REVIEW — PAGE
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionReviewPageDTO:
    """
    Очередь Human Review текущего учителя.

    teaching_scope нужен странице для отображения
    предметов, по которым учитель имеет право
    выполнять проверку.

    В дальнейшем источник scope может быть заменён
    с teaching assignments на subject expert assignments
    без изменения структуры страницы.
    """

    teaching_scope: list[
        TeacherQuestionBankTeachingScopeDTO
    ]

    items: list[
        TeacherQuestionReviewItemDTO
    ]

    total: int
