from __future__ import annotations

from app.modules.assessment.helpers.question_bank_expert_scope import review_scope_clause
from dataclasses import replace
from app.modules.assessment.repositories.learning_objective_formulation_repo import (
    LearningObjectiveFormulationRepo as Formulations,
)
# app/modules/assessment/repositories/teacher_question_bank_repo.py

from app.modules.assessment.repositories.learning_objective_quarter_queries import objective_display_title, objective_quarters_match, item_quarters_match

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.enums import (
    AssessmentLanguage,
    AssessmentQuestionDifficulty,
    AssessmentQuestionType,
    QuestionBankItemOrigin,
    QuestionBankItemStatus, QuestionBankReviewDecision,
)
from app.modules.assessment.models import (
    QuestionBankItem, QuestionBankLanguageVariant,
    QuestionBankItemObjective, LearningObjective, QuestionBankItemReview,
)
from app.modules.education.models import Subject, SchoolClass, SchoolClassSubjectTeacher
from app.modules.users.models import User
from app.modules.assessment.repositories.learning_objective_quarter_queries import objective_quarter_matches, \
    objective_quarter_for_validation, item_objective_quarter


# =========================================================
# READ MODELS
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankRow:
    """
    Строка Question Bank в рабочем кабинете учителя.

    Одна строка = один QuestionBankItem.

    Repository сразу возвращает все данные,
    необходимые для списка, без lazy loading
    и без N+1.
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


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankObjectiveRow:
    question_bank_item_id: int
    learning_objective_id: int

    quarter: int

    code: str
    title_kz: str
    title_ru: str | None

    order_no: int


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankReviewRow:
    review_id: int
    reviewer_user_id: int | None
    reviewer_name: str | None
    decision: QuestionBankReviewDecision
    comment: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankDetail:
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
    text_segments: list[dict[str, Any]]

    instruction: str | None

    content: dict[str, Any]
    answer_key: dict[str, Any]
    grading_settings: dict[str, Any]

    max_score: Decimal

    explanation: str | None
    author_comment: str | None

    created_at: datetime
    updated_at: datetime

    objectives: list[
        TeacherQuestionBankObjectiveRow
    ]

    reviews: list[
        TeacherQuestionBankReviewRow
    ]


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankTeachingScopeRow:
    """
    Разрешённая комбинация предмет + класс
    для текущего учителя.
    """

    subject_id: int
    subject_code: str

    subject_name_kz: str
    subject_name_ru: str | None

    grade_level: int


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankLearningObjectiveRow:
    """
    Учебная цель для выбранного
    предмета, класса и четверти.
    """

    learning_objective_id: int

    quarter: int

    code: str

    title_kz: str
    title_ru: str | None
    title_segments_kz: tuple[dict[str, str], ...] = ()
    title_segments_ru: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankObjectiveValidationRow:
    learning_objective_id: int
    subject_id: int
    grade_level: int
    quarter: int
    is_active: bool
    education_track: str = ""


# =========================================================
# CATALOG — READ MODEL
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionBankCatalogRow:
    """
    Задание общего Question Bank,
    доступное через каталог.

    Авторство не является ограничением выборки.
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
    text_segments: list[dict[str, Any]]

    instruction: str | None

    content: dict[str, Any]
    answer_key: dict[str, Any]
    grading_settings: dict[str, Any]
    explanation: str | None

    max_score: Decimal

    created_by_user_id: int | None
    author_name: str | None

    created_at: datetime
    updated_at: datetime


# =========================================================
# HUMAN REVIEW — READ MODEL
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherQuestionReviewRow:
    """
    Задание в очереди Human Review учителя.

    Это read-model рабочего кабинета.
    Lifecycle задания здесь не изменяется.
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
# REPOSITORY
# =========================================================


class TeacherQuestionBankRepo:
    @staticmethod
    async def list_catalog_variant_languages(db: AsyncSession, *, item_ids: list[int]):
        """Saved second-language rows for the visible page, in one query."""
        if not item_ids:
            return []
        return (await db.execute(select(
            QuestionBankLanguageVariant.item_id, QuestionBankLanguageVariant.language,
        ).where(QuestionBankLanguageVariant.item_id.in_(item_ids)))).all()

    """
        Repository Question Bank
        для рабочего кабинета учителя.

        Security boundary:

            created_by_user_id

        Учитель получает только те QuestionBankItem,
        которые были созданы его User.

        Repository:
            - выполняет чтение данных Question Bank;
            - создаёт DRAFT через teacher workflow;
            - не управляет lifecycle;
            - не выполняет commit / rollback;
            - не использует lazy loading;
            - не создаёт N+1.
        """

    # =====================================================
    # LIST
    # =====================================================

    @staticmethod
    async def list_subject_filters(db, *, user_id):
        # One bounded lookup for dropdown options, independent of row count.
        result = await db.execute(select(Subject.id, Subject.name_kz, Subject.name_ru).join(
            QuestionBankItem, QuestionBankItem.subject_id == Subject.id
        ).where(QuestionBankItem.created_by_user_id == user_id).distinct().order_by(Subject.id))
        return [dict(row) for row in result.mappings().all()]

    @staticmethod
    async def get_many_for_teacher(
            db: AsyncSession,
            *,
            created_by_user_id: int,
            status: QuestionBankItemStatus | None = None,
            filters: dict | None = None,
    ) -> list[TeacherQuestionBankRow]:
        """
        Получить собственные задания учителя.

        Фильтрация:
            created_by_user_id — обязательная;
            status — опциональная.

        Одна строка результата соответствует
        одному QuestionBankItem.

        Количество LearningObjective считается
        тем же SQL-запросом.

        Без lazy loading.
        Без N+1.
        """

        conditions = [
            QuestionBankItem.created_by_user_id
            == created_by_user_id,
        ]

        if status is not None:
            conditions.append(
                QuestionBankItem.status == status
            )

        filters = filters or {}
        for name in ('subject_id', 'grade_level', 'quarter', 'question_type', 'difficulty', 'language', 'origin'):
            value = filters.get(name)
            if value is not None and value != '':
                conditions.append(getattr(QuestionBankItem, name) == value)
        query = filters.get('q', '').strip()
        if query:
            from sqlalchemy import or_
            # User search characters are literal, not SQL wildcard operators.
            escaped = query.replace('!', '!!').replace('%', '!%').replace('_', '!_')
            pattern = '%' + escaped + '%'
            objective_match = select(QuestionBankItemObjective.id).join(
                LearningObjective, LearningObjective.id == QuestionBankItemObjective.learning_objective_id
            ).where(QuestionBankItemObjective.question_bank_item_id == QuestionBankItem.id,
                    LearningObjective.code.ilike(pattern, escape='!')).correlate(QuestionBankItem).exists()
            matches = [QuestionBankItem.title.ilike(pattern, escape='!'),
                       QuestionBankItem.text.ilike(pattern, escape='!'), objective_match]
            if query.isdecimal() and len(query) <= 10:
                matches.append(QuestionBankItem.id == int(query))
            conditions.append(or_(*matches))

        stmt = (
            select(
                # -----------------------------------------
                # QUESTION BANK ITEM
                # -----------------------------------------

                QuestionBankItem.id.label(
                    "item_id"
                ),

                QuestionBankItem.subject_id.label(
                    "subject_id"
                ),

                QuestionBankItem.grade_level.label(
                    "grade_level"
                ),

                QuestionBankItem.question_type.label(
                    "question_type"
                ),

                QuestionBankItem.difficulty.label(
                    "difficulty"
                ),

                QuestionBankItem.language.label(
                    "language"
                ),

                QuestionBankItem.status.label(
                    "status"
                ),

                QuestionBankItem.origin.label(
                    "origin"
                ),

                QuestionBankItem.title.label(
                    "title"
                ),

                QuestionBankItem.text.label(
                    "text"
                ),

                QuestionBankItem.created_at.label(
                    "created_at"
                ),

                QuestionBankItem.updated_at.label(
                    "updated_at"
                ),

                # -----------------------------------------
                # SUBJECT
                # -----------------------------------------

                func.coalesce(
                    Subject.name_ru,
                    Subject.name_kz,
                    "",
                ).label(
                    "subject_name"
                ),

                # -----------------------------------------
                # LEARNING OBJECTIVES
                # -----------------------------------------

                func.count(
                    QuestionBankItemObjective.id
                ).label(
                    "objective_count"
                ),
            )

            # =============================================
            # ITEM -> SUBJECT
            # =============================================

            .join(
                Subject,
                Subject.id
                == QuestionBankItem.subject_id,
            )

            # =============================================
            # ITEM -> OBJECTIVES
            # =============================================

            .outerjoin(
                QuestionBankItemObjective,
                QuestionBankItemObjective.question_bank_item_id
                == QuestionBankItem.id,
            )

            # =============================================
            # SECURITY / FILTERS
            # =============================================

            .where(
                *conditions
            )

            # =============================================
            # GROUP BY
            # =============================================

            .group_by(
                QuestionBankItem.id,
                QuestionBankItem.subject_id,
                QuestionBankItem.grade_level,
                QuestionBankItem.question_type,
                QuestionBankItem.difficulty,
                QuestionBankItem.language,
                QuestionBankItem.status,
                QuestionBankItem.origin,
                QuestionBankItem.title,
                QuestionBankItem.text,
                QuestionBankItem.created_at,
                QuestionBankItem.updated_at,
                Subject.name_ru,
                Subject.name_kz,
            )

            # =============================================
            # ORDER
            # =============================================

            .order_by(
                QuestionBankItem.updated_at.desc(),
                QuestionBankItem.id.desc(),
            )
        )

        result = await db.execute(stmt)

        rows = result.all()

        return [
            TeacherQuestionBankRow(
                item_id=row.item_id,

                subject_id=row.subject_id,
                subject_name=(
                        row.subject_name
                        or "—"
                ),

                grade_level=row.grade_level,

                question_type=row.question_type,
                difficulty=row.difficulty,
                language=row.language,

                status=row.status,
                origin=row.origin,

                title=row.title,
                text=row.text,

                objective_count=int(
                    row.objective_count or 0
                ),

                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    # =====================================================
    # CATALOG
    # =====================================================

    @staticmethod
    async def list_ready_catalog_scope(db):
        result = await db.execute(select(Subject.id.label('subject_id'),
            Subject.code.label('subject_code'), Subject.name_kz.label('subject_name_kz'),
            Subject.name_ru.label('subject_name_ru'), QuestionBankItem.grade_level
        ).join(QuestionBankItem, QuestionBankItem.subject_id == Subject.id).where(
            QuestionBankItem.status == QuestionBankItemStatus.READY
        ).distinct().order_by(Subject.id, QuestionBankItem.grade_level))
        return [TeacherQuestionBankTeachingScopeRow(**dict(row)) for row in result.mappings().all()]

    @staticmethod
    async def list_catalog_items(
            db: AsyncSession,
            *,
            subject_id: int,
            grade_level: int,
            objective_id: int | None = None,
            objective_ids: list[int] | None = None,
            quarter: int | None = None,
            limit: int | None = None, offset: int = 0,
            quarters: list[int] | None = None,
    ) -> list[TeacherQuestionBankCatalogRow]:
        """
        Возвращает задания общего Question Bank
        по предмету, параллели и учебной цели.

        ВАЖНО:
        created_by_user_id здесь намеренно
        НЕ используется как фильтр.

        Право текущего учителя работать с указанными
        subject_id + grade_level проверяет Service Layer
        через has_teaching_scope().

        В общий каталог попадают только READY задания.

        Один SQL-запрос.
        Lazy loading отсутствует.
        N+1 отсутствует.
        """

        stmt = (
            select(
                # -----------------------------------------
                # QUESTION BANK ITEM
                # -----------------------------------------

                QuestionBankItem.id.label(
                    "item_id"
                ),

                QuestionBankItem.subject_id.label(
                    "subject_id"
                ),

                QuestionBankItem.grade_level.label(
                    "grade_level"
                ),

                QuestionBankItem.question_type.label(
                    "question_type"
                ),

                QuestionBankItem.difficulty.label(
                    "difficulty"
                ),

                QuestionBankItem.language.label(
                    "language"
                ),

                QuestionBankItem.status.label(
                    "status"
                ),

                QuestionBankItem.origin.label(
                    "origin"
                ),

                QuestionBankItem.title.label(
                    "title"
                ),

                QuestionBankItem.text.label(
                    "text"
                ),

                QuestionBankItem.text_segments.label(
                    "text_segments"
                ),

                QuestionBankItem.instruction.label(
                    "instruction"
                ),

                QuestionBankItem.content.label(
                    "content"
                ),

                QuestionBankItem.answer_key.label(
                    "answer_key"
                ),

                QuestionBankItem.grading_settings.label("grading_settings"),
                QuestionBankItem.explanation.label("explanation"),

                QuestionBankItem.max_score.label(
                    "max_score"
                ),

                QuestionBankItem.created_by_user_id.label(
                    "created_by_user_id"
                ),

                QuestionBankItem.created_at.label(
                    "created_at"
                ),

                QuestionBankItem.updated_at.label(
                    "updated_at"
                ),

                # -----------------------------------------
                # SUBJECT
                # -----------------------------------------

                func.coalesce(
                    Subject.name_ru,
                    Subject.name_kz,
                    "",
                ).label(
                    "subject_name"
                ),

                # -----------------------------------------
                # AUTHOR
                # -----------------------------------------

                User.full_name.label(
                    "author_name"
                ),
            )

            # =============================================
            # ITEM -> SUBJECT
            # =============================================

            .join(
                Subject,
                Subject.id
                == QuestionBankItem.subject_id,
            )

            # =============================================
            # ITEM -> OBJECTIVE LINK
            # =============================================

            .join(
                QuestionBankItemObjective,
                QuestionBankItemObjective.question_bank_item_id
                == QuestionBankItem.id,
            )

            # =============================================
            # AUTHOR
            # =============================================
            .join(LearningObjective, LearningObjective.id == QuestionBankItemObjective.learning_objective_id)
            .outerjoin(
                User,
                User.id
                == QuestionBankItem.created_by_user_id,
            )

            # =============================================
            # FILTER
            # =============================================

            .where(
                QuestionBankItem.subject_id
                == subject_id,

                QuestionBankItem.grade_level
                == grade_level,

                QuestionBankItem.status
                == QuestionBankItemStatus.READY,

                (QuestionBankItemObjective.learning_objective_id == objective_id
                 if objective_id is not None else QuestionBankItemObjective.learning_objective_id.in_(objective_ids or [])),
                (func.coalesce(QuestionBankItem.quarter, LearningObjective.quarter) == quarter
                 if quarter is not None else True),
            )

            # =============================================
            # ORDER
            # =============================================

            .distinct()
            .order_by(
                QuestionBankItem.updated_at.desc(),
                QuestionBankItem.id.desc(),
            )
        )

        if quarters is not None:
            stmt=stmt.where(item_quarters_match(QuestionBankItem.__table__,quarters))
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)
        result = await db.execute(stmt)

        rows = result.all()

        return [
            TeacherQuestionBankCatalogRow(
                item_id=row.item_id,

                subject_id=row.subject_id,
                subject_name=(
                        row.subject_name
                        or "—"
                ),

                grade_level=row.grade_level,

                question_type=row.question_type,
                difficulty=row.difficulty,
                language=row.language,

                status=row.status,
                origin=row.origin,

                title=row.title,

                text=row.text,

                text_segments=[
                    dict(segment)
                    for segment in (
                            row.text_segments or []
                    )
                ],

                instruction=row.instruction,

                content=dict(
                    row.content or {}
                ),

                answer_key=dict(
                    row.answer_key or {}
                ),

                grading_settings=dict(row.grading_settings or {}),
                explanation=row.explanation,

                max_score=row.max_score,

                created_by_user_id=(
                    row.created_by_user_id
                ),

                author_name=(
                        row.author_name
                        or "—"
                ),

                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    # =====================================================
    # HUMAN REVIEW QUEUE
    # =====================================================

    @staticmethod
    async def list_review_queue(
            db: AsyncSession,
            *,
            reviewer_user_id: int,
            subject_ids: list[int],
    ) -> list[TeacherQuestionReviewRow]:
        """
        Возвращает очередь Human Review предметного эксперта.

        В очередь входят только:
        - задания в статусе REVIEW;
        - задания предметов, доступных эксперту;
        - задания, созданные другим пользователем.

        Repository не определяет глобальную роль reviewer.
        subject_ids передаются из expert scope.
        """

        if not subject_ids:
            return []

        stmt = (
            select(
                QuestionBankItem.id.label(
                    "item_id"
                ),

                QuestionBankItem.subject_id.label(
                    "subject_id"
                ),

                QuestionBankItem.grade_level.label(
                    "grade_level"
                ),

                QuestionBankItem.question_type.label(
                    "question_type"
                ),

                QuestionBankItem.difficulty.label(
                    "difficulty"
                ),

                QuestionBankItem.language.label(
                    "language"
                ),

                QuestionBankItem.status.label(
                    "status"
                ),

                QuestionBankItem.origin.label(
                    "origin"
                ),

                QuestionBankItem.title.label(
                    "title"
                ),

                QuestionBankItem.text.label(
                    "text"
                ),

                QuestionBankItem.text_segments.label(
                    "text_segments"
                ),

                QuestionBankItem.instruction.label(
                    "instruction"
                ),

                QuestionBankItem.content.label(
                    "content"
                ),

                QuestionBankItem.answer_key.label(
                    "answer_key"
                ),

                QuestionBankItem.grading_settings.label("grading_settings"),
                QuestionBankItem.explanation.label("explanation"),

                QuestionBankItem.max_score.label(
                    "max_score"
                ),

                QuestionBankItem.created_by_user_id.label(
                    "created_by_user_id"
                ),

                QuestionBankItem.created_at.label(
                    "created_at"
                ),

                QuestionBankItem.updated_at.label(
                    "updated_at"
                ),

                func.coalesce(
                    Subject.name_ru,
                    Subject.name_kz,
                    "",
                ).label(
                    "subject_name"
                ),

                User.full_name.label(
                    "author_name"
                ),
            )
            .join(
                Subject,
                Subject.id
                == QuestionBankItem.subject_id,
            )
            .outerjoin(
                User,
                User.id
                == QuestionBankItem.created_by_user_id,
            )
            .where(
                QuestionBankItem.status
                == QuestionBankItemStatus.REVIEW,

                QuestionBankItem.subject_id.in_(
                    subject_ids
                ),
                review_scope_clause(reviewer_user_id),

                QuestionBankItem.created_by_user_id.is_not(
                    None
                ),

                QuestionBankItem.created_by_user_id
                != reviewer_user_id,
            )
            .order_by(
                QuestionBankItem.updated_at.asc(),
                QuestionBankItem.id.asc(),
            )
        )

        result = await db.execute(stmt)

        rows = result.all()

        return [
            TeacherQuestionReviewRow(
                item_id=row.item_id,

                subject_id=row.subject_id,
                subject_name=(
                        row.subject_name
                        or "—"
                ),

                grade_level=row.grade_level,

                question_type=row.question_type,
                difficulty=row.difficulty,
                language=row.language,

                status=row.status,
                origin=row.origin,

                title=row.title,

                text=row.text,

                text_segments=[
                    dict(segment)
                    for segment in (
                            row.text_segments or []
                    )
                ],

                instruction=row.instruction,

                content=dict(
                    row.content or {}
                ),

                answer_key=dict(
                    row.answer_key or {}
                ),

                grading_settings=dict(row.grading_settings or {}),
                explanation=row.explanation,

                max_score=row.max_score,

                created_by_user_id=(
                    row.created_by_user_id
                ),

                author_name=(
                        row.author_name
                        or "—"
                ),

                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    @staticmethod
    async def get_review_item_for_reviewer(
            db: AsyncSession,
            *,
            item_id: int,
            reviewer_user_id: int,
            subject_ids: list[int],
    ) -> QuestionBankItem | None:
        """
        Возвращает задание, доступное текущему учителю
        для Human Review.

        Условия:
        - задание существует;
        - статус задания REVIEW;
        - у задания есть автор;
        - reviewer не является автором задания;
        - предмет задания входит в teaching scope reviewer.

        Метод:
        - не изменяет данные;
        - не выполняет commit/rollback;
        - возвращает None, если задание недоступно reviewer.
        """

        if not subject_ids:
            return None

        stmt = (
            select(QuestionBankItem)
            .where(
                QuestionBankItem.id == item_id,
                QuestionBankItem.status == QuestionBankItemStatus.REVIEW,
                QuestionBankItem.created_by_user_id.is_not(None),
                QuestionBankItem.created_by_user_id != reviewer_user_id,
                QuestionBankItem.subject_id.in_(subject_ids),
                review_scope_clause(reviewer_user_id),
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    @classmethod
    async def get_detail_for_teacher(
            cls,
            db: AsyncSession,
            *,
            item_id: int,
            created_by_user_id: int,
    ) -> TeacherQuestionBankDetail | None:
        """
        Получает полную карточку собственного задания учителя.

        Security boundary применяется непосредственно
        в SQL основного QuestionBankItem.

        Выполняется фиксированное количество запросов:
            1. QuestionBankItem + Subject
            2. LearningObjective
            3. Human Review history

        N+1 отсутствует.
        """

        item = await cls._get_detail_item(
            db,
            item_id=item_id,
            created_by_user_id=created_by_user_id,
        )

        if item is None:
            return None

        objectives = await cls.list_objectives_for_items(
            db,
            item_ids=[item_id],
        )

        reviews = await cls._get_detail_reviews(
            db,
            item_id=item_id,
        )

        return TeacherQuestionBankDetail(
            item_id=item.item_id,

            subject_id=item.subject_id,
            subject_name=item.subject_name or "—",

            grade_level=item.grade_level,
            question_type=item.question_type,
            difficulty=item.difficulty,
            language=item.language,
            status=item.status,
            origin=item.origin,

            title=item.title,

            text=item.text,
            text_segments=[
                dict(segment)
                for segment in (item.text_segments or [])
            ],
            instruction=item.instruction,

            content=item.content,
            answer_key=item.answer_key,
            grading_settings=item.grading_settings,

            max_score=item.max_score,
            explanation=item.explanation,
            author_comment=item.author_comment,

            created_at=item.created_at,
            updated_at=item.updated_at,

            objectives=objectives,
            reviews=reviews,
        )

    @staticmethod
    async def _get_detail_item(
            db: AsyncSession,
            *,
            item_id: int,
            created_by_user_id: int,
    ):
        """
        Возвращает основную часть полной карточки
        собственного задания учителя.

        Security boundary:
        QuestionBankItem ограничивается одновременно
        по item_id и created_by_user_id.
        """

        stmt = (
            select(
                QuestionBankItem.id.label("item_id"),
                QuestionBankItem.subject_id.label("subject_id"),
                QuestionBankItem.grade_level.label("grade_level"),

                QuestionBankItem.question_type.label("question_type"),
                QuestionBankItem.difficulty.label("difficulty"),
                QuestionBankItem.language.label("language"),
                QuestionBankItem.status.label("status"),
                QuestionBankItem.origin.label("origin"),

                QuestionBankItem.title.label("title"),
                QuestionBankItem.text.label("text"),
                QuestionBankItem.text_segments.label("text_segments"),
                QuestionBankItem.instruction.label("instruction"),

                QuestionBankItem.content.label("content"),
                QuestionBankItem.answer_key.label("answer_key"),
                QuestionBankItem.grading_settings.label(
                    "grading_settings"
                ),

                QuestionBankItem.max_score.label("max_score"),
                QuestionBankItem.explanation.label("explanation"),
                QuestionBankItem.author_comment.label(
                    "author_comment"
                ),

                QuestionBankItem.created_at.label("created_at"),
                QuestionBankItem.updated_at.label("updated_at"),

                func.coalesce(
                    Subject.name_ru,
                    Subject.name_kz,
                    "",
                ).label("subject_name"),
            )
            .join(
                Subject,
                Subject.id == QuestionBankItem.subject_id,
            )
            .where(
                QuestionBankItem.id == item_id,
                QuestionBankItem.created_by_user_id
                == created_by_user_id,
            )
        )

        result = await db.execute(stmt)

        return result.one_or_none()

    @staticmethod
    async def list_objectives_for_items(
            db: AsyncSession,
            *,
            item_ids: list[int],
    ) -> list[TeacherQuestionBankObjectiveRow]:
        """
        Возвращает учебные цели для набора QuestionBankItem.

        Один SQL-запрос независимо от количества заданий
        и количества LearningObjective.

        Используется:
            - DETAIL;
            - CATALOG;
            - HUMAN REVIEW.

        Lazy loading отсутствует.
        N+1 отсутствует.
        """

        if not item_ids:
            return []

        stmt = (
            select(
                QuestionBankItemObjective.question_bank_item_id.label(
                    "question_bank_item_id"
                ),

                LearningObjective.id.label(
                    "learning_objective_id"
                ),

                item_objective_quarter().label(
                    "quarter"
                ),

                LearningObjective.code.label(
                    "code"
                ),

                LearningObjective.title_kz.label(
                    "title_kz"
                ),

                LearningObjective.title_ru.label(
                    "title_ru"
                ),

                QuestionBankItemObjective.order_no.label(
                    "order_no"
                ),
            )
            .join(
                LearningObjective,
                LearningObjective.id
                == QuestionBankItemObjective.learning_objective_id,
            )
            .where(
                QuestionBankItemObjective.question_bank_item_id.in_(
                    item_ids
                )
            )
            .order_by(
                QuestionBankItemObjective.question_bank_item_id.asc(),
                QuestionBankItemObjective.order_no.asc(),
                LearningObjective.id.asc(),
            )
        )

        result = await db.execute(stmt)

        items = [
            TeacherQuestionBankObjectiveRow(
                question_bank_item_id=(
                    row.question_bank_item_id
                ),
                learning_objective_id=(
                    row.learning_objective_id
                ),
                quarter=row.quarter,
                code=row.code,
                title_kz=row.title_kz,
                title_ru=row.title_ru,
                order_no=row.order_no,
            )
            for row in result.all()
        ]

        forms = await Formulations.for_objectives(db,
                                                  objective_ids=list({item.learning_objective_id for item in items}))
        projected = []
        for item in items:
            changes = {}
            for language in ('kz', 'ru'):
                title, segments = Formulations.display(forms.get(item.learning_objective_id, []),
                                                       quarter=item.quarter, language=language)
                if title is not None:
                    old_title = getattr(item, 'title_' + language) or ''
                    suffix = next((label for label in (' [ЕМН]', ' [ОГН]') if old_title.endswith(label)), '')
                    changes['title_' + language] = title + suffix
                    if hasattr(item, 'title_segments_' + language):
                        changes['title_segments_' + language] = segments
                elif forms.get(item.learning_objective_id):
                    changes['title_' + language] = None if language == 'ru' else ''
                    if hasattr(item, 'title_segments_' + language):
                        changes['title_segments_' + language] = ()
            projected.append(replace(item, **changes))
        return projected

    @staticmethod
    async def _get_detail_reviews(
            db: AsyncSession,
            *,
            item_id: int,
    ) -> list[TeacherQuestionBankReviewRow]:
        """
        Получает полную историю Human Review.

        User подключается через OUTER JOIN, поскольку
        reviewer_user_id может стать NULL при удалении User.

        Один SQL-запрос независимо от количества review.
        Lazy loading и N+1 отсутствуют.
        """

        stmt = (
            select(
                QuestionBankItemReview.id.label(
                    "review_id"
                ),
                QuestionBankItemReview.reviewer_user_id.label(
                    "reviewer_user_id"
                ),
                User.full_name.label(
                    "reviewer_name"
                ),
                QuestionBankItemReview.decision.label(
                    "decision"
                ),
                QuestionBankItemReview.comment.label(
                    "comment"
                ),
                QuestionBankItemReview.created_at.label(
                    "created_at"
                ),
            )
            .outerjoin(
                User,
                User.id
                == QuestionBankItemReview.reviewer_user_id,
            )
            .where(
                QuestionBankItemReview.question_bank_item_id
                == item_id,
            )
            .order_by(
                QuestionBankItemReview.created_at.desc(),
                QuestionBankItemReview.id.desc(),
            )
        )

        result = await db.execute(stmt)

        rows = result.all()

        return [
            TeacherQuestionBankReviewRow(
                review_id=row.review_id,
                reviewer_user_id=row.reviewer_user_id,
                reviewer_name=row.reviewer_name,
                decision=row.decision,
                comment=row.comment,
                created_at=row.created_at,
            )
            for row in rows
        ]

    @staticmethod
    async def list_teaching_scope(
            db: AsyncSession,
            *,
            staff_member_id: int,
    ) -> list[TeacherQuestionBankTeachingScopeRow]:
        """
        Возвращает активные комбинации
        предмет + класс текущего учителя.

        Несколько параллелей одного grade_level
        сворачиваются через DISTINCT.

        Например:
            9A + Информатика
            9B + Информатика

        превращаются в:
            Информатика + 9
        """

        stmt = (
            select(
                Subject.id.label(
                    "subject_id"
                ),
                Subject.code.label(
                    "subject_code"
                ),
                Subject.name_kz.label(
                    "subject_name_kz"
                ),
                Subject.name_ru.label(
                    "subject_name_ru"
                ),
                SchoolClass.grade_level.label(
                    "grade_level"
                ),
            )
            .select_from(
                SchoolClassSubjectTeacher
            )
            .join(
                SchoolClass,
                SchoolClass.id
                == SchoolClassSubjectTeacher.school_class_id,
            )
            .join(
                Subject,
                Subject.id
                == SchoolClassSubjectTeacher.subject_id,
            )
            .where(
                SchoolClassSubjectTeacher.staff_member_id
                == staff_member_id,
                SchoolClassSubjectTeacher.is_active.is_(True),
                SchoolClass.is_active.is_(True),
                Subject.is_active.is_(True),
            )
            .distinct()
            .order_by(
                Subject.name_kz.asc(),
                SchoolClass.grade_level.asc(),
                Subject.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return [
            TeacherQuestionBankTeachingScopeRow(
                subject_id=row.subject_id,
                subject_code=row.subject_code,
                subject_name_kz=row.subject_name_kz,
                subject_name_ru=row.subject_name_ru,
                grade_level=row.grade_level,
            )
            for row in result.all()
        ]

    @staticmethod
    async def list_learning_objectives(
            db: AsyncSession,
            *,
            subject_id: int,
            grade_level: int,
            quarter: int | None,
            education_track: str | None = None,
            quarters: list[int] | None = None,
    ) -> list[TeacherQuestionBankLearningObjectiveRow]:
        """
        Возвращает активные учебные цели
        выбранного предмета, класса и четверти.
        """

        stmt = (
            select(
                LearningObjective.id.label(
                    "learning_objective_id"
                ),
                (objective_quarter_for_validation(quarter) if quarter is not None else LearningObjective.quarter).label(
                    "quarter"
                ),
                LearningObjective.code.label(
                    "code"
                ),
                LearningObjective.title_segments_kz.label("title_segments_kz"),
                LearningObjective.title_segments_ru.label("title_segments_ru"),
                objective_display_title("kz").label(
                    "title_kz"
                ),
                objective_display_title("ru").label(
                    "title_ru"
                ),
            )
            .where(
                LearningObjective.subject_id
                == subject_id,
                LearningObjective.grade_level
                == grade_level,
                (objective_quarters_match(quarters) if quarters is not None else
                 objective_quarter_matches(quarter) if quarter is not None else True),
                LearningObjective.education_track.in_(['', education_track]) if education_track is not None else True,
                LearningObjective.is_active.is_(True),
            )
            .order_by(
                LearningObjective.code.asc(),
                LearningObjective.id.asc(),
            )
        )

        result = await db.execute(stmt)

        items = [
            TeacherQuestionBankLearningObjectiveRow(
                learning_objective_id=(
                    row.learning_objective_id
                ),
                quarter=row.quarter,
                code=row.code,
                title_kz=row.title_kz,
                title_ru=row.title_ru,
                title_segments_kz=tuple(row.title_segments_kz or []),
                title_segments_ru=tuple(row.title_segments_ru or []),
            )
            for row in result.all()
        ]

        forms = await Formulations.for_objectives(db,
                                                  objective_ids=list({item.learning_objective_id for item in items}))
        projected = []
        for item in items:
            changes = {}
            for language in ('kz', 'ru'):
                title, segments = Formulations.display(forms.get(item.learning_objective_id, []),
                                                       quarter=quarter, language=language, quarters=quarters)
                if title is not None:
                    old_title = getattr(item, 'title_' + language) or ''
                    suffix = next((label for label in (' [ЕМН]', ' [ОГН]') if old_title.endswith(label)), '')
                    changes['title_' + language] = title + suffix
                    if hasattr(item, 'title_segments_' + language):
                        changes['title_segments_' + language] = segments
                elif forms.get(item.learning_objective_id):
                    changes['title_' + language] = None if language == 'ru' else ''
                    if hasattr(item, 'title_segments_' + language):
                        changes['title_segments_' + language] = ()
            projected.append(replace(item, **changes))
        return projected

    @staticmethod
    async def list_objectives_for_validation(
            db: AsyncSession,
            *,
            objective_ids: list[int], quarter: int | None = None,
    ) -> list[TeacherQuestionBankObjectiveValidationRow]:
        """
        Загружает все выбранные LearningObjective одним запросом.

        Метод намеренно не делает запросов по одному objective_id.
        """

        if not objective_ids:
            return []

        stmt = (
            select(
                LearningObjective.id.label(
                    "learning_objective_id"
                ),
                LearningObjective.subject_id.label(
                    "subject_id"
                ),
                LearningObjective.grade_level.label(
                    "grade_level"
                ),
                (LearningObjective.quarter if quarter is None else objective_quarter_for_validation(quarter)).label(
                    "quarter"
                ),
                LearningObjective.education_track.label("education_track"),
                LearningObjective.is_active.label(
                    "is_active"
                ),
            )
            .where(
                LearningObjective.id.in_(
                    objective_ids
                )
            )
            .order_by(
                LearningObjective.id.asc()
            )
        )

        result = await db.execute(stmt)

        return [
            TeacherQuestionBankObjectiveValidationRow(
                learning_objective_id=(
                    row.learning_objective_id
                ),
                subject_id=row.subject_id,
                grade_level=row.grade_level,
                quarter=row.quarter,
                is_active=row.is_active,
                education_track=row.education_track,
            )
            for row in result.all()
        ]

    @staticmethod
    async def has_teaching_scope(
            db: AsyncSession,
            *,
            staff_member_id: int,
            subject_id: int,
            grade_level: int,
    ) -> bool:
        """
        Проверяет, имеет ли преподаватель активное
        назначение на указанный предмет и класс.
        """

        stmt = (
            select(
                SchoolClassSubjectTeacher.id
            )
            .join(
                SchoolClass,
                SchoolClass.id
                == SchoolClassSubjectTeacher.school_class_id,
            )
            .join(
                Subject,
                Subject.id
                == SchoolClassSubjectTeacher.subject_id,
            )
            .where(
                SchoolClassSubjectTeacher.staff_member_id
                == staff_member_id,
                SchoolClassSubjectTeacher.subject_id
                == subject_id,
                SchoolClass.grade_level
                == grade_level,

                SchoolClassSubjectTeacher.is_active.is_(True),
                SchoolClass.is_active.is_(True),
                Subject.is_active.is_(True),
            )
            .limit(1)
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none() is not None

    @staticmethod
    async def create_draft(
            db: AsyncSession,
            *,
            subject_id: int,
            grade_level: int,
            question_type: AssessmentQuestionType,
            difficulty: AssessmentQuestionDifficulty,
            language: AssessmentLanguage,
            title: str | None,
            text: str,
            text_segments: list[dict[str, Any]],
            instruction: str | None,
            content: dict[str, Any],
            answer_key: dict[str, Any],
            grading_settings: dict[str, Any],
            max_score: Decimal,
            explanation: str | None,
            author_comment: str | None,
            created_by_user_id: int,
            objective_ids: list[int], quarter: int | None = None,
    ) -> QuestionBankItem:
        """
        Создаёт QuestionBankItem DRAFT вместе
        со связями LearningObjective.

        Commit здесь намеренно не выполняется.
        Транзакцией управляет Service Layer.
        """

        item = QuestionBankItem(
            subject_id=subject_id,
            grade_level=grade_level,

            question_type=question_type,
            difficulty=difficulty,
            language=language,

            status=QuestionBankItemStatus.DRAFT,
            origin=QuestionBankItemOrigin.MANUAL,

            title=title,

            text=text,
            text_segments=[
                dict(segment)
                for segment in text_segments
            ],

            instruction=instruction,

            content=content,
            answer_key=answer_key,
            grading_settings=grading_settings,

            max_score=max_score,

            explanation=explanation,
            author_comment=author_comment,

            created_by_user_id=created_by_user_id,
            quarter=quarter,
        )

        db.add(item)

        # Нужен ID родительской записи.
        # Это INSERT, не SELECT.
        await db.flush()

        objective_links = [
            QuestionBankItemObjective(
                question_bank_item_id=item.id,
                learning_objective_id=objective_id,
                order_no=order_no,
            )
            for order_no, objective_id in enumerate(
                objective_ids,
                start=1,
            )
        ]

        db.add_all(objective_links)

        await db.flush()

        return item

    @staticmethod
    async def update_draft(
            db: AsyncSession,
            *,
            item: QuestionBankItem,
            subject_id: int,
            grade_level: int,
            question_type: AssessmentQuestionType,
            difficulty: AssessmentQuestionDifficulty,
            language: AssessmentLanguage,
            title: str | None,
            text: str,
            text_segments: list[dict[str, Any]],
            instruction: str | None,
            content: dict[str, Any],
            answer_key: dict[str, Any],
            grading_settings: dict[str, Any],
            max_score: Decimal,
            explanation: str | None,
            author_comment: str | None,
            objective_ids: list[int], quarter: int | None = None,
    ) -> QuestionBankItem:
        """
        Обновляет содержимое существующего задания учителя
        и полностью заменяет связи LearningObjective.

        Repository:
            - не проверяет ownership;
            - не проверяет lifecycle;
            - не выполняет commit / rollback.

        Ownership, допустимый статус и переход lifecycle
        контролирует Service Layer.
        """

        # =====================================================
        # 1. UPDATE QUESTION BANK ITEM
        # =====================================================

        item.quarter = quarter
        item.subject_id = subject_id
        item.grade_level = grade_level

        item.question_type = question_type
        item.difficulty = difficulty
        item.language = language

        item.title = title

        item.text = text
        item.text_segments = [
            dict(segment)
            for segment in text_segments
        ]

        item.instruction = instruction

        item.content = dict(content)
        item.answer_key = dict(answer_key)
        item.grading_settings = dict(grading_settings)

        item.max_score = max_score

        item.explanation = explanation
        item.author_comment = author_comment

        # =====================================================
        # 2. REMOVE OLD OBJECTIVE LINKS
        # =====================================================

        await db.execute(
            delete(QuestionBankItemObjective)
            .where(
                QuestionBankItemObjective.question_bank_item_id
                == item.id
            )
        )

        # =====================================================
        # 3. CREATE CURRENT OBJECTIVE LINKS
        # =====================================================

        objective_links = [
            QuestionBankItemObjective(
                question_bank_item_id=item.id,
                learning_objective_id=objective_id,
                order_no=order_no,
            )
            for order_no, objective_id in enumerate(
                objective_ids,
                start=1,
            )
        ]

        db.add_all(objective_links)

        await db.flush()

        return item

    @staticmethod
    async def get_item_for_teacher(
            db: AsyncSession,
            *,
            item_id: int,
            created_by_user_id: int,
    ) -> QuestionBankItem | None:
        """
        Возвращает ORM QuestionBankItem,
        принадлежащий текущему учителю.

        Используется write-side сценариями.

        Repository не проверяет lifecycle.
        """

        stmt = (
            select(QuestionBankItem)
            .where(
                QuestionBankItem.id == item_id,
                QuestionBankItem.created_by_user_id
                == created_by_user_id,
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()
