# app/modules/assessment/repositories/knowledge_quality_analytics_repo.py

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select, false, cast, String, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.models import (
    AssessmentQualitySummary, Assessment,
)


# =========================================================
# RAW AGGREGATE
# =========================================================


@dataclass(frozen=True, slots=True)
class KnowledgeQualityAggregateRow:
    """
    Унифицированный результат SQL-агрегации.

    Проценты и средние здесь намеренно не считаются.
    Их рассчитывает KnowledgeQualityCalculator.
    """

    total_students: int
    participated_students: int

    absent_students: int
    excused_students: int
    not_completed_students: int

    grade_5_count: int
    grade_4_count: int
    grade_3_count: int
    grade_2_count: int

    score_sum: Decimal
    percent_sum: Decimal


@dataclass(frozen=True, slots=True)
class KnowledgeQualityClassAggregateRow:
    """
    Для класса SQL-агрегат для drill-down аналитики.
    """

    school_class_id: int
    class_name: str
    grade_level: int

    total_students: int
    participated_students: int

    absent_students: int
    excused_students: int
    not_completed_students: int

    grade_5_count: int
    grade_4_count: int
    grade_3_count: int
    grade_2_count: int

    score_sum: Decimal
    percent_sum: Decimal


@dataclass(frozen=True, slots=True)
class KnowledgeQualityGroupedAggregateRow:
    """
    SQL-агрегат для drill-down аналитики.

    entity_id:
        school_id   — для районной аналитики;
        district_id — для региональной аналитики.
    """

    entity_id: int

    total_students: int
    participated_students: int

    absent_students: int
    excused_students: int
    not_completed_students: int

    grade_5_count: int
    grade_4_count: int
    grade_3_count: int
    grade_2_count: int

    score_sum: Decimal
    percent_sum: Decimal


@dataclass(frozen=True, slots=True)
class KnowledgeQualityFilterOptionsRow:
    """
    Доступные измерения аналитики.

    Значения получены непосредственно из
    AssessmentQualitySummary.
    """

    academic_years: tuple[int, ...]
    subject_ids: tuple[int, ...]
    grade_levels: tuple[int, ...]


class KnowledgeQualityAnalyticsRepo:
    """
    Высокопроизводительная аналитика качества знаний.

    Работает исключительно через
    AssessmentQualitySummary.

    Не читает:
        AssessmentStudent
        AssessmentResult

    Поддерживает уровни:
        school
        district
        region
    """

    # =====================================================
    # INTERNAL
    # =====================================================

    @staticmethod
    def _checkpoint_rank():
        return case(*[(AssessmentQualitySummary.checkpoint_snapshot == name, index)
                      for index,name in enumerate(('baseline','quarter_1','quarter_2','quarter_3','quarter_4','final'))], else_=6)

    @classmethod
    async def get_all_work_rows(cls, db, *, scope, scope_id, teacher_staff_member_id=None,
                                academic_year_start=None, subject_id=None, grade_level=None,
                                checkpoint='', offset=0, limit=51):
        from app.modules.assessment.repositories.assessment_name_columns import title_column
        from app.modules.assessment.models_diagnostic_sessions import DiagnosticSubject
        q, a = AssessmentQualitySummary, Assessment
        logical_id = func.coalesce(a.diagnostic_subject_id, -a.id)
        entity = q.school_class_id if scope in ('teacher', 'school') else q.school_id if scope == 'district' else q.district_id_snapshot
        stmt = (select(logical_id.label('logical_id'), entity.label('entity_id'),
                    func.min(title_column()).label('work_title'),
                    func.min(cast(q.checkpoint_snapshot, String)).label('checkpoint'),
                    func.min(q.class_name_snapshot).label('class_name'),
                    func.min(DiagnosticSubject.session_id).label('session_id'),
                    *cls._aggregate_columns())
                .select_from(q).join(a, (a.id == q.assessment_id) & (a.school_id == q.school_id))
                .outerjoin(DiagnosticSubject, DiagnosticSubject.id == a.diagnostic_subject_id))
        if not scope_id or scope_id <= 0 or academic_year_start is None:return []
        if scope == 'teacher':
            if not teacher_staff_member_id or teacher_staff_member_id <= 0:return []
            stmt = stmt.where(q.school_id == scope_id, q.teacher_staff_member_id_snapshot == teacher_staff_member_id)
        elif scope == 'school':stmt = stmt.where(q.school_id == scope_id)
        elif scope == 'district':stmt = stmt.where(q.district_id_snapshot == scope_id)
        elif scope == 'region':stmt = stmt.where(q.region_id_snapshot == scope_id, entity.is_not(None))
        else:raise ValueError('Invalid analytics scope')
        stmt = stmt.where(q.academic_year_start_snapshot == academic_year_start)
        if subject_id is not None:stmt = stmt.where(q.subject_id == subject_id)
        if grade_level is not None:stmt = stmt.where(q.grade_level_snapshot == grade_level)
        if checkpoint == 'other':stmt = stmt.where(q.checkpoint_snapshot.is_(None))
        elif checkpoint in ('baseline','quarter_1','quarter_2','quarter_3','quarter_4','final'):
            stmt = stmt.where(q.checkpoint_snapshot == checkpoint)
        elif checkpoint:return []
        rank = cls._checkpoint_rank()
        stmt = stmt.group_by(logical_id, entity).order_by(func.min(rank).asc(),
            func.max(a.completed_at).asc().nullslast(), logical_id.asc(), entity.asc())
        stmt = stmt.offset(max(0, offset)).limit(min(max(1, limit), 50001))
        return [dict(row._mapping) for row in (await db.execute(stmt)).all()]

    @staticmethod
    def _apply_work_filter(stmt, work_key):
        """One logical work; summary counters and existing scope stay unchanged."""
        if work_key is None:
            return stmt  # Existing internal callers retain their explicit aggregate semantics.
        kind, sep, raw = work_key.partition(':')
        if sep != ':' or kind not in ('a', 'd') or not raw.isascii() or not raw.isdigit() or len(raw) > 10 or not 0 < int(raw) <= 2147483647:
            return stmt.where(false())
        condition = (Assessment.diagnostic_subject_id == int(raw)) if kind == 'd' else (Assessment.id == int(raw))
        return stmt.where(AssessmentQualitySummary.assessment_id.in_(
            select(Assessment.id).where(condition)))

    @staticmethod
    async def get_work_choices(db, *, scope, scope_id, teacher_staff_member_id=None,
                               academic_year_start=None, subject_id=None, grade_level=None,
                               checkpoint='', search=''):
        """Bounded, school/teacher scoped selector, one SQL independent of variant count."""
        from app.modules.assessment.repositories.assessment_name_columns import title_column
        from app.modules.assessment.models_diagnostic_sessions import DiagnosticSubject
        q, a = AssessmentQualitySummary, Assessment
        logical_id = func.coalesce(a.diagnostic_subject_id, -a.id)
        stmt = (select(logical_id.label('logical_id'), func.min(title_column()).label('title'),
                    func.max(a.completed_at).label('completed_at'),
                    func.min(cast(q.checkpoint_snapshot, String)).label('checkpoint'),
                    func.min(DiagnosticSubject.session_id).label('session_id'),
                    func.count(func.distinct(q.school_class_id)).label('classes'))
                .select_from(q).join(a, (a.id == q.assessment_id) & (a.school_id == q.school_id))
                .outerjoin(DiagnosticSubject, DiagnosticSubject.id == a.diagnostic_subject_id))
        if scope == 'teacher':
            if not teacher_staff_member_id or teacher_staff_member_id <= 0:
                return []
            stmt = stmt.where(q.school_id == scope_id,
                             q.teacher_staff_member_id_snapshot == teacher_staff_member_id)
        elif scope == 'school':stmt = stmt.where(q.school_id == scope_id)
        elif scope == 'district':stmt = stmt.where(q.district_id_snapshot == scope_id)
        elif scope == 'region':stmt = stmt.where(q.region_id_snapshot == scope_id)
        else:raise ValueError('Invalid analytics scope')
        if not scope_id or scope_id <= 0 or academic_year_start is None:return []
        stmt = stmt.where(q.academic_year_start_snapshot == academic_year_start)
        if subject_id is not None:stmt = stmt.where(q.subject_id == subject_id)
        if grade_level is not None:stmt = stmt.where(q.grade_level_snapshot == grade_level)
        if checkpoint == 'other':stmt = stmt.where(q.checkpoint_snapshot.is_(None))
        elif checkpoint:stmt = stmt.where(q.checkpoint_snapshot == checkpoint)
        if search:stmt = stmt.where(title_column().icontains(search, autoescape=True))
        stmt = stmt.group_by(logical_id).order_by(func.min(KnowledgeQualityAnalyticsRepo._checkpoint_rank()).asc(), func.max(a.completed_at).asc().nullslast(), logical_id.asc()).limit(201)
        return [dict(row._mapping) for row in (await db.execute(stmt)).all()]

    @staticmethod
    def _aggregate_columns():
        return (
            func.coalesce(
                func.sum(
                    AssessmentQualitySummary.total_students
                ),
                0,
            ).label(
                "total_students"
            ),

            func.coalesce(
                func.sum(
                    AssessmentQualitySummary.participated_students
                ),
                0,
            ).label(
                "participated_students"
            ),

            func.coalesce(
                func.sum(
                    AssessmentQualitySummary.absent_students
                ),
                0,
            ).label(
                "absent_students"
            ),

            func.coalesce(
                func.sum(
                    AssessmentQualitySummary.excused_students
                ),
                0,
            ).label(
                "excused_students"
            ),

            func.coalesce(
                func.sum(
                    AssessmentQualitySummary.not_completed_students
                ),
                0,
            ).label(
                "not_completed_students"
            ),

            func.coalesce(
                func.sum(
                    AssessmentQualitySummary.grade_5_count
                ),
                0,
            ).label(
                "grade_5_count"
            ),

            func.coalesce(
                func.sum(
                    AssessmentQualitySummary.grade_4_count
                ),
                0,
            ).label(
                "grade_4_count"
            ),

            func.coalesce(
                func.sum(
                    AssessmentQualitySummary.grade_3_count
                ),
                0,
            ).label(
                "grade_3_count"
            ),

            func.coalesce(
                func.sum(
                    AssessmentQualitySummary.grade_2_count
                ),
                0,
            ).label(
                "grade_2_count"
            ),

            func.coalesce(
                func.sum(
                    AssessmentQualitySummary.score_sum
                ),
                0,
            ).label(
                "score_sum"
            ),

            func.coalesce(
                func.sum(
                    AssessmentQualitySummary.percent_sum
                ),
                0,
            ).label(
                "percent_sum"
            ),
        )

    @staticmethod
    def _row_to_dto(
            row,
    ) -> KnowledgeQualityAggregateRow:
        return KnowledgeQualityAggregateRow(
            total_students=int(
                row.total_students or 0
            ),

            participated_students=int(
                row.participated_students or 0
            ),

            absent_students=int(
                row.absent_students or 0
            ),

            excused_students=int(
                row.excused_students or 0
            ),

            not_completed_students=int(
                row.not_completed_students or 0
            ),

            grade_5_count=int(
                row.grade_5_count or 0
            ),

            grade_4_count=int(
                row.grade_4_count or 0
            ),

            grade_3_count=int(
                row.grade_3_count or 0
            ),

            grade_2_count=int(
                row.grade_2_count or 0
            ),

            score_sum=Decimal(
                row.score_sum or 0
            ),

            percent_sum=Decimal(
                row.percent_sum or 0
            ),
        )

    @staticmethod
    def _row_to_class_dto(
            row,
    ) -> KnowledgeQualityClassAggregateRow:
        return KnowledgeQualityClassAggregateRow(
            school_class_id=int(
                row.school_class_id
            ),

            class_name=(
                    row.class_name
                    or f"ID {row.school_class_id}"
            ),

            grade_level=int(
                row.grade_level
            ),

            total_students=int(
                row.total_students or 0
            ),

            participated_students=int(
                row.participated_students or 0
            ),

            absent_students=int(
                row.absent_students or 0
            ),

            excused_students=int(
                row.excused_students or 0
            ),

            not_completed_students=int(
                row.not_completed_students or 0
            ),

            grade_5_count=int(
                row.grade_5_count or 0
            ),

            grade_4_count=int(
                row.grade_4_count or 0
            ),

            grade_3_count=int(
                row.grade_3_count or 0
            ),

            grade_2_count=int(
                row.grade_2_count or 0
            ),

            score_sum=Decimal(
                row.score_sum or 0
            ),

            percent_sum=Decimal(
                row.percent_sum or 0
            ),
        )

    @staticmethod
    def _row_to_grouped_dto(
            row,
    ) -> KnowledgeQualityGroupedAggregateRow:
        return KnowledgeQualityGroupedAggregateRow(
            entity_id=int(
                row.entity_id
            ),

            total_students=int(
                row.total_students or 0
            ),

            participated_students=int(
                row.participated_students or 0
            ),

            absent_students=int(
                row.absent_students or 0
            ),

            excused_students=int(
                row.excused_students or 0
            ),

            not_completed_students=int(
                row.not_completed_students or 0
            ),

            grade_5_count=int(
                row.grade_5_count or 0
            ),

            grade_4_count=int(
                row.grade_4_count or 0
            ),

            grade_3_count=int(
                row.grade_3_count or 0
            ),

            grade_2_count=int(
                row.grade_2_count or 0
            ),

            score_sum=Decimal(
                row.score_sum or 0
            ),

            percent_sum=Decimal(
                row.percent_sum or 0
            ),
        )

    # =====================================================
    # FILTER OPTIONS INTERNAL
    # =====================================================

    @staticmethod
    async def _get_filter_options(
            db: AsyncSession,
            *,
            conditions: tuple,
    ) -> KnowledgeQualityFilterOptionsRow:
        """
        Общий builder доступных измерений аналитики.

        Источник:
            AssessmentQualitySummary

        Выполняет фиксированное количество SQL-запросов:
            1. academic years;
            2. subjects;
            3. grade levels.

        N+1 отсутствует.
        """

        # =====================================================
        # ACADEMIC YEARS
        # =====================================================

        academic_year_stmt = (
            select(
                AssessmentQualitySummary
                .academic_year_start_snapshot
            )
            .where(
                *conditions
            )
            .distinct()
            .order_by(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                .desc()
            )
        )

        academic_year_result = (
            await db.execute(
                academic_year_stmt
            )
        )

        academic_years = tuple(
            int(row[0])
            for row in academic_year_result.all()
            if row[0] is not None
        )

        # =====================================================
        # SUBJECTS
        # =====================================================

        subject_stmt = (
            select(
                AssessmentQualitySummary.subject_id
            )
            .where(
                *conditions
            )
            .distinct()
            .order_by(
                AssessmentQualitySummary
                .subject_id
                .asc()
            )
        )

        subject_result = (
            await db.execute(
                subject_stmt
            )
        )

        subject_ids = tuple(
            int(row[0])
            for row in subject_result.all()
            if row[0] is not None
        )

        # =====================================================
        # GRADE LEVELS
        # =====================================================

        grade_level_stmt = (
            select(
                AssessmentQualitySummary
                .grade_level_snapshot
            )
            .where(
                *conditions
            )
            .distinct()
            .order_by(
                AssessmentQualitySummary
                .grade_level_snapshot
                .asc()
            )
        )

        grade_level_result = (
            await db.execute(
                grade_level_stmt
            )
        )

        grade_levels = tuple(
            int(row[0])
            for row in grade_level_result.all()
            if row[0] is not None
        )

        return KnowledgeQualityFilterOptionsRow(
            academic_years=academic_years,
            subject_ids=subject_ids,
            grade_levels=grade_levels,
        )

    # =====================================================
    # SCHOOL -> CLASSES
    # =====================================================

    @classmethod
    async def get_school_class_rows(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            work_key: str | None = None,
    ) -> list[KnowledgeQualityClassAggregateRow]:
        """
        Аналитика школы с группировкой по классам.

        Источник:
            AssessmentQualitySummary

        AssessmentStudent / AssessmentResult
        не загружаются.
        """

        stmt = (
            select(
                AssessmentQualitySummary
                .school_class_id
                .label(
                    "school_class_id"
                ),

                AssessmentQualitySummary
                .class_name_snapshot
                .label(
                    "class_name"
                ),

                AssessmentQualitySummary
                .grade_level_snapshot
                .label(
                    "grade_level"
                ),

                *cls._aggregate_columns(),
            )
            .select_from(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary.school_id
                == school_id
            )
        )

        # =====================================================
        # FILTERS
        # =====================================================

        if academic_year_start is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                == academic_year_start
            )

        if subject_id is not None:
            stmt = stmt.where(
                AssessmentQualitySummary.subject_id
                == subject_id
            )

        if grade_level is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .grade_level_snapshot
                == grade_level
            )

        # =====================================================
        # GROUP / ORDER
        # =====================================================

        stmt = (
            stmt
            .group_by(
                AssessmentQualitySummary.school_class_id,

                AssessmentQualitySummary
                .class_name_snapshot,

                AssessmentQualitySummary
                .grade_level_snapshot,
            )
            .order_by(
                AssessmentQualitySummary
                .grade_level_snapshot
                .asc(),

                AssessmentQualitySummary
                .class_name_snapshot
                .asc(),

                AssessmentQualitySummary
                .school_class_id
                .asc(),
            )
        )

        # =====================================================
        # EXECUTE
        # =====================================================

        stmt = KnowledgeQualityAnalyticsRepo._apply_work_filter(stmt, work_key)

        rows = (
            await db.execute(
                stmt
            )
        ).all()

        return [
            cls._row_to_class_dto(
                row
            )
            for row in rows
        ]

    # =====================================================
    # TEACHER SUMMARY
    # =====================================================

    @classmethod
    async def get_teacher_summary(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            work_key: str | None = None,
    ) -> KnowledgeQualityAggregateRow:
        """
        Общая аналитика конкретного учителя.

        Источник:
            AssessmentQualitySummary

        Обязательная security boundary:
            school_id
            teacher_staff_member_id

        AssessmentStudent / AssessmentResult
        не загружаются.
        """

        stmt = (
            select(
                *cls._aggregate_columns()
            )
            .select_from(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary.school_id
                == school_id,

                AssessmentQualitySummary
                .teacher_staff_member_id_snapshot
                == teacher_staff_member_id,
            )
        )

        if academic_year_start is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                == academic_year_start
            )

        if subject_id is not None:
            stmt = stmt.where(
                AssessmentQualitySummary.subject_id
                == subject_id
            )

        if grade_level is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .grade_level_snapshot
                == grade_level
            )

        stmt = KnowledgeQualityAnalyticsRepo._apply_work_filter(stmt, work_key)

        row = (
            await db.execute(
                stmt
            )
        ).one()

        return cls._row_to_dto(
            row
        )

    # =====================================================
    # SCHOOL -> CLASS TEACHERS
    # =====================================================

    @staticmethod
    async def get_school_class_teacher_names(
            db: AsyncSession,
            *,
            school_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            work_key: str | None = None,
    ) -> dict[int, tuple[str, ...]]:
        """
        Получить учителей по классам
        для school export.

        Источник:
            AssessmentQualitySummary.teacher_name_snapshot

        Один SQL-запрос.

        Один класс может иметь несколько учителей,
        особенно если subject_id=None.
        """

        stmt = (
            select(
                AssessmentQualitySummary.school_class_id,
                AssessmentQualitySummary.teacher_name_snapshot,
            )
            .where(
                AssessmentQualitySummary.school_id
                == school_id,

                AssessmentQualitySummary.teacher_name_snapshot
                .is_not(None),
            )
        )

        if academic_year_start is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                == academic_year_start
            )

        if subject_id is not None:
            stmt = stmt.where(
                AssessmentQualitySummary.subject_id
                == subject_id
            )

        if grade_level is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .grade_level_snapshot
                == grade_level
            )

        stmt = (
            stmt
            .distinct()
            .order_by(
                AssessmentQualitySummary.school_class_id.asc(),
                AssessmentQualitySummary.teacher_name_snapshot.asc(),
            )
        )

        stmt = KnowledgeQualityAnalyticsRepo._apply_work_filter(stmt, work_key)

        result = await db.execute(
            stmt
        )

        teachers_by_class: dict[
            int,
            list[str],
        ] = {}

        for row in result.all():
            school_class_id = int(
                row.school_class_id
            )

            teacher_name = str(
                row.teacher_name_snapshot
            ).strip()

            if not teacher_name:
                continue

            teachers_by_class.setdefault(
                school_class_id,
                [],
            ).append(
                teacher_name
            )

        return {
            school_class_id: tuple(
                teacher_names
            )
            for (
                school_class_id,
                teacher_names,
            ) in teachers_by_class.items()
        }

    # =====================================================
    # SCHOOL FILTER OPTIONS
    # =====================================================

    @classmethod
    async def get_school_filter_options(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
    ) -> KnowledgeQualityFilterOptionsRow:
        """
        Реально доступные фильтры аналитики школы.

        Возвращаются только значения,
        которые существуют в AssessmentQualitySummary
        текущей школы.

        Источник:
            AssessmentQualitySummary
        """

        return await cls._get_filter_options(
            db,
            conditions=(
                AssessmentQualitySummary.school_id
                == school_id,
            ),
        )

    # =====================================================
    # SCHOOL
    # =====================================================

    @classmethod
    async def get_school_summary(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            work_key: str | None = None,
    ) -> KnowledgeQualityAggregateRow:
        stmt = (
            select(
                *cls._aggregate_columns()
            )
            .select_from(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary.school_id
                == school_id
            )
        )

        if academic_year_start is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                == academic_year_start
            )

        if subject_id is not None:
            stmt = stmt.where(
                AssessmentQualitySummary.subject_id
                == subject_id
            )

        if grade_level is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .grade_level_snapshot
                == grade_level
            )

        stmt = KnowledgeQualityAnalyticsRepo._apply_work_filter(stmt, work_key)

        row = (
            await db.execute(stmt)
        ).one()

        return cls._row_to_dto(
            row
        )

    # =====================================================
    # DISTRICT
    # =====================================================

    @classmethod
    async def get_district_summary(
            cls,
            db: AsyncSession,
            *,
            district_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            school_id: int | None = None,
        work_key: str | None = None,
    ) -> KnowledgeQualityAggregateRow:
        stmt = (
            select(
                *cls._aggregate_columns()
            )
            .select_from(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary
                .district_id_snapshot
                == district_id
            )
        )

        if academic_year_start is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                == academic_year_start
            )

        if subject_id is not None:
            stmt = stmt.where(
                AssessmentQualitySummary.subject_id
                == subject_id
            )

        if grade_level is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .grade_level_snapshot
                == grade_level
            )

        if school_id is not None:
            stmt = stmt.where(
                AssessmentQualitySummary.school_id
                == school_id
            )

        stmt = KnowledgeQualityAnalyticsRepo._apply_work_filter(stmt, work_key)

        row = (
            await db.execute(stmt)
        ).one()

        return cls._row_to_dto(
            row
        )

    # =====================================================
    # REGION
    # =====================================================

    @classmethod
    async def get_region_summary(
            cls,
            db: AsyncSession,
            *,
            region_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            district_id: int | None = None,
            school_id: int | None = None,
        work_key: str | None = None,
    ) -> KnowledgeQualityAggregateRow:
        stmt = (
            select(
                *cls._aggregate_columns()
            )
            .select_from(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary
                .region_id_snapshot
                == region_id
            )
        )

        if academic_year_start is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                == academic_year_start
            )

        if subject_id is not None:
            stmt = stmt.where(
                AssessmentQualitySummary.subject_id
                == subject_id
            )

        if grade_level is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .grade_level_snapshot
                == grade_level
            )

        if district_id is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .district_id_snapshot
                == district_id
            )

        if school_id is not None:
            stmt = stmt.where(
                AssessmentQualitySummary.school_id
                == school_id
            )

        stmt = KnowledgeQualityAnalyticsRepo._apply_work_filter(stmt, work_key)

        row = (
            await db.execute(stmt)
        ).one()

        return cls._row_to_dto(
            row
        )

    # =====================================================
    # TEACHER -> CLASSES
    # =====================================================

    @classmethod
    async def get_teacher_class_rows(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            work_key: str | None = None,
    ) -> list[KnowledgeQualityClassAggregateRow]:
        """
        Аналитика учителя с группировкой по классам.

        Одна строка результата = один класс,
        по которому у данного учителя существуют
        AssessmentQualitySummary.

        Источник:
            AssessmentQualitySummary
        """

        stmt = (
            select(
                AssessmentQualitySummary
                .school_class_id
                .label(
                    "school_class_id"
                ),

                AssessmentQualitySummary
                .class_name_snapshot
                .label(
                    "class_name"
                ),

                AssessmentQualitySummary
                .grade_level_snapshot
                .label(
                    "grade_level"
                ),

                *cls._aggregate_columns(),
            )
            .select_from(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary.school_id
                == school_id,

                AssessmentQualitySummary
                .teacher_staff_member_id_snapshot
                == teacher_staff_member_id,
            )
        )

        if academic_year_start is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                == academic_year_start
            )

        if subject_id is not None:
            stmt = stmt.where(
                AssessmentQualitySummary.subject_id
                == subject_id
            )

        if grade_level is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .grade_level_snapshot
                == grade_level
            )

        stmt = (
            stmt
            .group_by(
                AssessmentQualitySummary
                .school_class_id,

                AssessmentQualitySummary
                .class_name_snapshot,

                AssessmentQualitySummary
                .grade_level_snapshot,
            )
            .order_by(
                AssessmentQualitySummary
                .grade_level_snapshot
                .asc(),

                AssessmentQualitySummary
                .class_name_snapshot
                .asc(),

                AssessmentQualitySummary
                .school_class_id
                .asc(),
            )
        )

        stmt = KnowledgeQualityAnalyticsRepo._apply_work_filter(stmt, work_key)

        rows = (
            await db.execute(
                stmt
            )
        ).all()

        return [
            cls._row_to_class_dto(
                row
            )
            for row in rows
        ]

    # =====================================================
    # TEACHER FILTER OPTIONS
    # =====================================================

    @staticmethod
    async def get_teacher_filter_options(
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
    ) -> KnowledgeQualityFilterOptionsRow:
        """
        Реально доступные фильтры аналитики учителя.

        Возвращаются только значения,
        которые существуют в AssessmentQualitySummary
        данного учителя внутри текущей школы.

        Источник:
            AssessmentQualitySummary
        """

        base_conditions = (
            AssessmentQualitySummary.school_id
            == school_id,

            AssessmentQualitySummary
            .teacher_staff_member_id_snapshot
            == teacher_staff_member_id,
        )

        # =================================================
        # ACADEMIC YEARS
        # =================================================

        academic_year_stmt = (
            select(
                AssessmentQualitySummary
                .academic_year_start_snapshot
            )
            .where(
                *base_conditions
            )
            .distinct()
            .order_by(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                .desc()
            )
        )

        academic_year_result = (
            await db.execute(
                academic_year_stmt
            )
        )

        academic_years = tuple(
            int(value)
            for value
            in academic_year_result.scalars().all()
        )

        # =================================================
        # SUBJECTS
        # =================================================

        subject_stmt = (
            select(
                AssessmentQualitySummary.subject_id
            )
            .where(
                *base_conditions
            )
            .distinct()
            .order_by(
                AssessmentQualitySummary
                .subject_id
                .asc()
            )
        )

        subject_result = (
            await db.execute(
                subject_stmt
            )
        )

        subject_ids = tuple(
            int(value)
            for value
            in subject_result.scalars().all()
        )

        # =================================================
        # GRADE LEVELS
        # =================================================

        grade_level_stmt = (
            select(
                AssessmentQualitySummary
                .grade_level_snapshot
            )
            .where(
                *base_conditions
            )
            .distinct()
            .order_by(
                AssessmentQualitySummary
                .grade_level_snapshot
                .asc()
            )
        )

        grade_level_result = (
            await db.execute(
                grade_level_stmt
            )
        )

        grade_levels = tuple(
            int(value)
            for value
            in grade_level_result.scalars().all()
        )

        return KnowledgeQualityFilterOptionsRow(
            academic_years=(
                academic_years
            ),
            subject_ids=(
                subject_ids
            ),
            grade_levels=(
                grade_levels
            ),
        )

    # =====================================================
    # DISTRICT → SCHOOLS
    # =====================================================

    @classmethod
    async def get_district_school_rows(
            cls,
            db: AsyncSession,
            *,
            district_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            work_key: str | None = None,
    ) -> list[KnowledgeQualityGroupedAggregateRow]:
        """
        Аналитика района с группировкой по школам.

        Один SQL-запрос.
        AssessmentResult не читается.
        """

        stmt = (
            select(
                AssessmentQualitySummary.school_id.label(
                    "entity_id"
                ),
                *cls._aggregate_columns(),
            )
            .select_from(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary
                .district_id_snapshot
                == district_id
            )
        )

        if academic_year_start is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                == academic_year_start
            )

        if subject_id is not None:
            stmt = stmt.where(
                AssessmentQualitySummary.subject_id
                == subject_id
            )

        if grade_level is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .grade_level_snapshot
                == grade_level
            )

        stmt = (
            stmt
            .group_by(
                AssessmentQualitySummary.school_id
            )
            .order_by(
                AssessmentQualitySummary.school_id.asc()
            )
        )

        stmt = KnowledgeQualityAnalyticsRepo._apply_work_filter(stmt, work_key)

        rows = (
            await db.execute(stmt)
        ).all()

        return [
            cls._row_to_grouped_dto(row)
            for row in rows
        ]

    # =====================================================
    # REGION → DISTRICTS
    # =====================================================

    @classmethod
    async def get_region_district_rows(
            cls,
            db: AsyncSession,
            *,
            region_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            work_key: str | None = None,
    ) -> list[KnowledgeQualityGroupedAggregateRow]:
        """
        Аналитика региона с группировкой по районам.
        """

        stmt = (
            select(
                AssessmentQualitySummary
                .district_id_snapshot
                .label(
                    "entity_id"
                ),
                *cls._aggregate_columns(),
            )
            .select_from(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary
                .region_id_snapshot
                == region_id,

                # В региональной таблице строка
                # должна принадлежать району.
                AssessmentQualitySummary
                .district_id_snapshot
                .is_not(None),
            )
        )

        if academic_year_start is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                == academic_year_start
            )

        if subject_id is not None:
            stmt = stmt.where(
                AssessmentQualitySummary.subject_id
                == subject_id
            )

        if grade_level is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .grade_level_snapshot
                == grade_level
            )

        stmt = (
            stmt
            .group_by(
                AssessmentQualitySummary
                .district_id_snapshot
            )
            .order_by(
                AssessmentQualitySummary
                .district_id_snapshot
                .asc()
            )
        )

        stmt = KnowledgeQualityAnalyticsRepo._apply_work_filter(stmt, work_key)

        rows = (
            await db.execute(stmt)
        ).all()

        return [
            cls._row_to_grouped_dto(row)
            for row in rows
        ]

    # =====================================================
    # DISTRICT FILTER OPTIONS
    # =====================================================

    @staticmethod
    async def get_district_filter_options(
            db: AsyncSession,
            *,
            district_id: int,
    ) -> KnowledgeQualityFilterOptionsRow:
        """
        Реально доступные фильтры районной аналитики.

        Источник:
            AssessmentQualitySummary

        Возвращаются только значения, по которым
        в районе существуют аналитические snapshot-строки.
        """

        # =================================================
        # ACADEMIC YEARS
        # =================================================

        academic_year_stmt = (
            select(
                AssessmentQualitySummary
                .academic_year_start_snapshot
            )
            .where(
                AssessmentQualitySummary
                .district_id_snapshot
                == district_id
            )
            .distinct()
            .order_by(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                .desc()
            )
        )

        academic_year_result = (
            await db.execute(
                academic_year_stmt
            )
        )

        academic_years = tuple(
            int(value)
            for value
            in academic_year_result.scalars().all()
        )

        # =================================================
        # SUBJECTS
        # =================================================

        subject_stmt = (
            select(
                AssessmentQualitySummary.subject_id
            )
            .where(
                AssessmentQualitySummary
                .district_id_snapshot
                == district_id
            )
            .distinct()
            .order_by(
                AssessmentQualitySummary
                .subject_id
                .asc()
            )
        )

        subject_result = (
            await db.execute(
                subject_stmt
            )
        )

        subject_ids = tuple(
            int(value)
            for value
            in subject_result.scalars().all()
        )

        # =================================================
        # GRADE LEVELS
        # =================================================

        grade_level_stmt = (
            select(
                AssessmentQualitySummary
                .grade_level_snapshot
            )
            .where(
                AssessmentQualitySummary
                .district_id_snapshot
                == district_id
            )
            .distinct()
            .order_by(
                AssessmentQualitySummary
                .grade_level_snapshot
                .asc()
            )
        )

        grade_level_result = (
            await db.execute(
                grade_level_stmt
            )
        )

        grade_levels = tuple(
            int(value)
            for value
            in grade_level_result.scalars().all()
        )

        return KnowledgeQualityFilterOptionsRow(
            academic_years=academic_years,
            subject_ids=subject_ids,
            grade_levels=grade_levels,
        )

    # =====================================================
    # REGION FILTER OPTIONS
    # =====================================================

    @staticmethod
    async def get_region_filter_options(
            db: AsyncSession,
            *,
            region_id: int,
    ) -> KnowledgeQualityFilterOptionsRow:
        """
        Реально доступные фильтры региональной аналитики.

        Источник:
            AssessmentQualitySummary

        Возвращаются только значения, по которым
        в регионе существуют аналитические snapshot-строки.
        """

        # =================================================
        # ACADEMIC YEARS
        # =================================================

        academic_year_stmt = (
            select(
                AssessmentQualitySummary
                .academic_year_start_snapshot
            )
            .where(
                AssessmentQualitySummary
                .region_id_snapshot
                == region_id
            )
            .distinct()
            .order_by(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                .desc()
            )
        )

        academic_year_result = (
            await db.execute(
                academic_year_stmt
            )
        )

        academic_years = tuple(
            int(value)
            for value
            in academic_year_result.scalars().all()
        )

        # =================================================
        # SUBJECTS
        # =================================================

        subject_stmt = (
            select(
                AssessmentQualitySummary.subject_id
            )
            .where(
                AssessmentQualitySummary
                .region_id_snapshot
                == region_id
            )
            .distinct()
            .order_by(
                AssessmentQualitySummary
                .subject_id
                .asc()
            )
        )

        subject_result = (
            await db.execute(
                subject_stmt
            )
        )

        subject_ids = tuple(
            int(value)
            for value
            in subject_result.scalars().all()
        )

        # =================================================
        # GRADE LEVELS
        # =================================================

        grade_level_stmt = (
            select(
                AssessmentQualitySummary
                .grade_level_snapshot
            )
            .where(
                AssessmentQualitySummary
                .region_id_snapshot
                == region_id
            )
            .distinct()
            .order_by(
                AssessmentQualitySummary
                .grade_level_snapshot
                .asc()
            )
        )

        grade_level_result = (
            await db.execute(
                grade_level_stmt
            )
        )

        grade_levels = tuple(
            int(value)
            for value
            in grade_level_result.scalars().all()
        )

        return KnowledgeQualityFilterOptionsRow(
            academic_years=academic_years,
            subject_ids=subject_ids,
            grade_levels=grade_levels,
        )
