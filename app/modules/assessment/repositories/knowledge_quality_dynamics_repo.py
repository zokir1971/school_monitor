# app/modules/assessment/repositories/knowledge_quality_dynamics_repo.py

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.enums import AssessmentCheckpoint
from app.modules.assessment.models import (
    AssessmentQualitySummary,
)


# =========================================================
# RAW ROWS
# =========================================================


@dataclass(frozen=True, slots=True)
class KnowledgeQualityDynamicsRow:
    """
    Сырые агрегированные данные одной контрольной точки.

    Repository не рассчитывает:
        - quality_percent;
        - delta vs previous;
        - delta vs baseline.

    Эти расчёты выполняет Service Layer.

    participated_students является знаменателем
    качества знаний.

    quality_students:
        grade_5_count + grade_4_count
    """

    checkpoint: AssessmentCheckpoint

    total_students: int
    participated_students: int

    grade_5_count: int
    grade_4_count: int

    quality_students: int


@dataclass(frozen=True, slots=True)
class KnowledgeQualityEntityDynamicsRow:
    """
    Сырые данные динамики для drill-down сущности.

    entity_id:
        school_id   — district -> schools;
        district_id — region -> districts.

    Одна строка:
        entity + checkpoint.
    """

    entity_id: int
    checkpoint: AssessmentCheckpoint

    total_students: int
    participated_students: int

    grade_5_count: int
    grade_4_count: int

    quality_students: int


@dataclass(frozen=True, slots=True)
class KnowledgeQualityDynamicsFilterRow:
    """
    Одна доступная комбинация фильтров динамики.

    Источник:
        AssessmentQualitySummary

    В выборку попадают только строки,
    относящиеся к официальным контрольным точкам:
        checkpoint_snapshot IS NOT NULL
    """

    academic_year_start: int
    subject_id: int
    grade_level: int


class KnowledgeQualityDynamicsRepo:
    """
    Репозиторий динамики качества знаний.

    Источник:
        AssessmentQualitySummary

    Используются только официальные контрольные точки:

        checkpoint_snapshot IS NOT NULL

    Поддерживаемые уровни:

        SCHOOL
            subject
            -> grade
            -> class
            -> teacher

        DISTRICT
            subject
            -> grade
            -> school

        REGION
            subject
            -> grade
            -> district
            -> school

    Repository:
        - выполняет SQL;
        - агрегирует счётчики;
        - не рассчитывает проценты;
        - не рассчитывает динамику;
        - не выполняет commit.
    """

    # =====================================================
    # INTERNAL
    # =====================================================

    @staticmethod
    def _aggregate_columns():
        """
        Общие SQL-агрегаты для одной контрольной точки.
        """

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

            (
                    func.coalesce(
                        func.sum(
                            AssessmentQualitySummary.grade_5_count
                        ),
                        0,
                    )
                    +
                    func.coalesce(
                        func.sum(
                            AssessmentQualitySummary.grade_4_count
                        ),
                        0,
                    )
            ).label(
                "quality_students"
            ),
        )

    @staticmethod
    def _row_to_dynamics(
            row,
    ) -> KnowledgeQualityDynamicsRow:
        return KnowledgeQualityDynamicsRow(
            checkpoint=row.checkpoint,

            total_students=int(
                row.total_students or 0
            ),

            participated_students=int(
                row.participated_students or 0
            ),

            grade_5_count=int(
                row.grade_5_count or 0
            ),

            grade_4_count=int(
                row.grade_4_count or 0
            ),

            quality_students=int(
                row.quality_students or 0
            ),
        )

    @staticmethod
    def _row_to_entity_dynamics(
            row,
    ) -> KnowledgeQualityEntityDynamicsRow:
        return KnowledgeQualityEntityDynamicsRow(
            entity_id=int(
                row.entity_id
            ),

            checkpoint=row.checkpoint,

            total_students=int(
                row.total_students or 0
            ),

            participated_students=int(
                row.participated_students or 0
            ),

            grade_5_count=int(
                row.grade_5_count or 0
            ),

            grade_4_count=int(
                row.grade_4_count or 0
            ),

            quality_students=int(
                row.quality_students or 0
            ),
        )

    # =====================================================
    # SCHOOL
    # =====================================================

    @classmethod
    async def get_school_filter_rows(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
    ) -> list[KnowledgeQualityDynamicsFilterRow]:
        """
        Доступные комбинации фильтров школьной динамики.

        Важно:
            берутся только AssessmentQualitySummary,
            у которых checkpoint_snapshot IS NOT NULL.

        Один SQL-запрос возвращает уникальные комбинации:
            academic_year_start + subject_id + grade_level.

        Далее Service Layer строит каскадные filter options
        без дополнительных SQL-запросов.
        """

        stmt = (
            select(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                .label(
                    "academic_year_start"
                ),

                AssessmentQualitySummary
                .subject_id
                .label(
                    "subject_id"
                ),

                AssessmentQualitySummary
                .grade_level_snapshot
                .label(
                    "grade_level"
                ),
            )
            .select_from(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary.school_id
                == school_id,

                AssessmentQualitySummary
                .checkpoint_snapshot
                .is_not(None),

                AssessmentQualitySummary.subject_id
                .is_not(None),

                AssessmentQualitySummary
                .grade_level_snapshot
                .is_not(None),
            )
            .distinct()
            .order_by(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                .desc(),

                AssessmentQualitySummary.subject_id
                .asc(),

                AssessmentQualitySummary
                .grade_level_snapshot
                .asc(),
            )
        )

        rows = (
            await db.execute(
                stmt
            )
        ).all()

        return [
            KnowledgeQualityDynamicsFilterRow(
                academic_year_start=int(
                    row.academic_year_start
                ),
                subject_id=int(
                    row.subject_id
                ),
                grade_level=int(
                    row.grade_level
                ),
            )
            for row in rows
        ]

    @classmethod
    async def get_school_checkpoint_rows(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            academic_year_start: int,
            subject_id: int | None = None,
            grade_level: int | None = None,
            school_class_id: int | None = None,
            teacher_staff_member_id: int | None = None,
    ) -> list[KnowledgeQualityDynamicsRow]:
        """
        Динамика качества знаний школы.

        Группировка:
            checkpoint

        Drill-down поддерживает:
            school
            -> subject
            -> grade
            -> class
            -> teacher
        """

        stmt = (
            select(
                AssessmentQualitySummary
                .checkpoint_snapshot
                .label(
                    "checkpoint"
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
                .academic_year_start_snapshot
                == academic_year_start,

                AssessmentQualitySummary
                .checkpoint_snapshot
                .is_not(None),
            )
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

        if school_class_id is not None:
            stmt = stmt.where(
                AssessmentQualitySummary.school_class_id
                == school_class_id
            )

        if teacher_staff_member_id is not None:
            stmt = stmt.where(
                AssessmentQualitySummary
                .teacher_staff_member_id_snapshot
                == teacher_staff_member_id
            )

        stmt = (
            stmt
            .group_by(
                AssessmentQualitySummary
                .checkpoint_snapshot
            )
            .order_by(
                AssessmentQualitySummary
                .checkpoint_snapshot
                .asc()
            )
        )

        rows = (
            await db.execute(
                stmt
            )
        ).all()

        return [
            cls._row_to_dynamics(
                row
            )
            for row in rows
        ]

    # =====================================================
    # SCHOOL -> CLASSES
    # =====================================================

    @classmethod
    async def get_school_class_checkpoint_rows(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            academic_year_start: int,
            subject_id: int | None = None,
            grade_level: int | None = None,
    ) -> list[KnowledgeQualityEntityDynamicsRow]:
        """
        Динамика школы с разбивкой по классам.

        Одна SQL-строка:
            school_class_id + checkpoint

        Используется школьной аналитикой для пакетного
        построения динамики всех классов без N+1.
        """

        stmt = (
            select(
                AssessmentQualitySummary
                .school_class_id
                .label(
                    "entity_id"
                ),

                AssessmentQualitySummary
                .checkpoint_snapshot
                .label(
                    "checkpoint"
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
                .school_class_id
                .is_not(None),

                AssessmentQualitySummary
                .academic_year_start_snapshot
                == academic_year_start,

                AssessmentQualitySummary
                .checkpoint_snapshot
                .is_not(None),
            )
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
                AssessmentQualitySummary.school_class_id,

                AssessmentQualitySummary
                .checkpoint_snapshot,
            )
            .order_by(
                AssessmentQualitySummary.school_class_id.asc(),

                AssessmentQualitySummary
                .checkpoint_snapshot
                .asc(),
            )
        )

        rows = (
            await db.execute(
                stmt
            )
        ).all()

        return [
            cls._row_to_entity_dynamics(
                row
            )
            for row in rows
        ]

    # =====================================================
    # DISTRICT
    # =====================================================

    @classmethod
    async def get_district_filter_rows(
            cls,
            db: AsyncSession,
            *,
            district_id: int,
    ) -> list[KnowledgeQualityDynamicsFilterRow]:
        """
        Доступные комбинации фильтров динамики района.

        Используются только официальные контрольные точки:

            checkpoint_snapshot IS NOT NULL

        Один SQL-запрос:
            academic_year_start + subject_id + grade_level
        """

        stmt = (
            select(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                .label(
                    "academic_year_start"
                ),

                AssessmentQualitySummary
                .subject_id
                .label(
                    "subject_id"
                ),

                AssessmentQualitySummary
                .grade_level_snapshot
                .label(
                    "grade_level"
                ),
            )
            .select_from(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary
                .district_id_snapshot
                == district_id,

                AssessmentQualitySummary
                .checkpoint_snapshot
                .is_not(None),

                AssessmentQualitySummary.subject_id
                .is_not(None),

                AssessmentQualitySummary
                .grade_level_snapshot
                .is_not(None),
            )
            .distinct()
            .order_by(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                .desc(),

                AssessmentQualitySummary.subject_id
                .asc(),

                AssessmentQualitySummary
                .grade_level_snapshot
                .asc(),
            )
        )

        rows = (
            await db.execute(
                stmt
            )
        ).all()

        return [
            KnowledgeQualityDynamicsFilterRow(
                academic_year_start=int(
                    row.academic_year_start
                ),
                subject_id=int(
                    row.subject_id
                ),
                grade_level=int(
                    row.grade_level
                ),
            )
            for row in rows
        ]

    @classmethod
    async def get_district_checkpoint_rows(
            cls,
            db: AsyncSession,
            *,
            district_id: int,
            academic_year_start: int,
            subject_id: int | None = None,
            grade_level: int | None = None,
            school_id: int | None = None,
    ) -> list[KnowledgeQualityDynamicsRow]:
        """
        Общая динамика района.

        Группировка:
            checkpoint

        Допустимый drill-down:
            district
            -> subject
            -> grade
            -> school

        Ни класс, ни учитель сюда не передаются.
        """

        stmt = (
            select(
                AssessmentQualitySummary
                .checkpoint_snapshot
                .label(
                    "checkpoint"
                ),

                *cls._aggregate_columns(),
            )
            .select_from(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary
                .district_id_snapshot
                == district_id,

                AssessmentQualitySummary
                .academic_year_start_snapshot
                == academic_year_start,

                AssessmentQualitySummary
                .checkpoint_snapshot
                .is_not(None),
            )
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

        stmt = (
            stmt
            .group_by(
                AssessmentQualitySummary
                .checkpoint_snapshot
            )
            .order_by(
                AssessmentQualitySummary
                .checkpoint_snapshot
                .asc()
            )
        )

        rows = (
            await db.execute(
                stmt
            )
        ).all()

        return [
            cls._row_to_dynamics(
                row
            )
            for row in rows
        ]

    # =====================================================
    # DISTRICT -> SCHOOLS
    # =====================================================

    @classmethod
    async def get_district_school_checkpoint_rows(
            cls,
            db: AsyncSession,
            *,
            district_id: int,
            academic_year_start: int,
            subject_id: int | None = None,
            grade_level: int | None = None,
    ) -> list[KnowledgeQualityEntityDynamicsRow]:
        """
        Динамика района с разбивкой по школам.

        Одна SQL-строка:
            school_id + checkpoint

        Используется, чтобы район мог определить,
        в какой школе возник рост или снижение.
        """

        stmt = (
            select(
                AssessmentQualitySummary
                .school_id
                .label(
                    "entity_id"
                ),

                AssessmentQualitySummary
                .checkpoint_snapshot
                .label(
                    "checkpoint"
                ),

                *cls._aggregate_columns(),
            )
            .select_from(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary
                .district_id_snapshot
                == district_id,

                AssessmentQualitySummary
                .academic_year_start_snapshot
                == academic_year_start,

                AssessmentQualitySummary
                .checkpoint_snapshot
                .is_not(None),
            )
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
                AssessmentQualitySummary.school_id,

                AssessmentQualitySummary
                .checkpoint_snapshot,
            )
            .order_by(
                AssessmentQualitySummary.school_id.asc(),

                AssessmentQualitySummary
                .checkpoint_snapshot
                .asc(),
            )
        )

        rows = (
            await db.execute(
                stmt
            )
        ).all()

        return [
            cls._row_to_entity_dynamics(
                row
            )
            for row in rows
        ]

    # =====================================================
    # REGION
    # =====================================================

    @classmethod
    async def get_region_filter_rows(
            cls,
            db: AsyncSession,
            *,
            region_id: int,
    ) -> list[KnowledgeQualityDynamicsFilterRow]:
        """
        Доступные комбинации фильтров динамики региона.

        Используются только официальные
        контрольные точки:

            checkpoint_snapshot IS NOT NULL

        Один SQL-запрос:
            academic_year_start + subject_id + grade_level
        """

        stmt = (
            select(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                .label(
                    "academic_year_start"
                ),

                AssessmentQualitySummary
                .subject_id
                .label(
                    "subject_id"
                ),

                AssessmentQualitySummary
                .grade_level_snapshot
                .label(
                    "grade_level"
                ),
            )
            .select_from(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary
                .region_id_snapshot
                == region_id,

                AssessmentQualitySummary
                .checkpoint_snapshot
                .is_not(None),

                AssessmentQualitySummary
                .subject_id
                .is_not(None),

                AssessmentQualitySummary
                .grade_level_snapshot
                .is_not(None),
            )
            .distinct()
            .order_by(
                AssessmentQualitySummary
                .academic_year_start_snapshot
                .desc(),

                AssessmentQualitySummary
                .subject_id
                .asc(),

                AssessmentQualitySummary
                .grade_level_snapshot
                .asc(),
            )
        )

        rows = (
            await db.execute(
                stmt
            )
        ).all()

        return [
            KnowledgeQualityDynamicsFilterRow(
                academic_year_start=int(
                    row.academic_year_start
                ),
                subject_id=int(
                    row.subject_id
                ),
                grade_level=int(
                    row.grade_level
                ),
            )
            for row in rows
        ]

    @classmethod
    async def get_region_checkpoint_rows(
            cls,
            db: AsyncSession,
            *,
            region_id: int,
            academic_year_start: int,
            subject_id: int | None = None,
            grade_level: int | None = None,
            district_id: int | None = None,
            school_id: int | None = None,
    ) -> list[KnowledgeQualityDynamicsRow]:
        """
        Общая динамика региона.

        Drill-down:
            region
            -> subject
            -> grade
            -> district
            -> school
        """

        stmt = (
            select(
                AssessmentQualitySummary
                .checkpoint_snapshot
                .label(
                    "checkpoint"
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

                AssessmentQualitySummary
                .academic_year_start_snapshot
                == academic_year_start,

                AssessmentQualitySummary
                .checkpoint_snapshot
                .is_not(None),
            )
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

        stmt = (
            stmt
            .group_by(
                AssessmentQualitySummary
                .checkpoint_snapshot
            )
            .order_by(
                AssessmentQualitySummary
                .checkpoint_snapshot
                .asc()
            )
        )

        rows = (
            await db.execute(
                stmt
            )
        ).all()

        return [
            cls._row_to_dynamics(
                row
            )
            for row in rows
        ]

    # =====================================================
    # REGION -> DISTRICTS
    # =====================================================

    @classmethod
    async def get_region_district_checkpoint_rows(
            cls,
            db: AsyncSession,
            *,
            region_id: int,
            academic_year_start: int,
            subject_id: int | None = None,
            grade_level: int | None = None,
    ) -> list[KnowledgeQualityEntityDynamicsRow]:
        """
        Динамика региона с разбивкой по районам.

        Одна SQL-строка:
            district_id + checkpoint
        """

        stmt = (
            select(
                AssessmentQualitySummary
                .district_id_snapshot
                .label(
                    "entity_id"
                ),

                AssessmentQualitySummary
                .checkpoint_snapshot
                .label(
                    "checkpoint"
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

                AssessmentQualitySummary
                .district_id_snapshot
                .is_not(None),

                AssessmentQualitySummary
                .academic_year_start_snapshot
                == academic_year_start,

                AssessmentQualitySummary
                .checkpoint_snapshot
                .is_not(None),
            )
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
                .district_id_snapshot,

                AssessmentQualitySummary
                .checkpoint_snapshot,
            )
            .order_by(
                AssessmentQualitySummary
                .district_id_snapshot
                .asc(),

                AssessmentQualitySummary
                .checkpoint_snapshot
                .asc(),
            )
        )

        rows = (
            await db.execute(
                stmt
            )
        ).all()

        return [
            cls._row_to_entity_dynamics(
                row
            )
            for row in rows
        ]

    # =====================================================
    # REGION -> DISTRICT -> SCHOOLS
    # =====================================================

    @classmethod
    async def get_region_school_checkpoint_rows(
            cls,
            db: AsyncSession,
            *,
            region_id: int,
            district_id: int,
            academic_year_start: int,
            subject_id: int | None = None,
            grade_level: int | None = None,
    ) -> list[KnowledgeQualityEntityDynamicsRow]:
        """
        Динамика школ конкретного района
        внутри региональной аналитики.

        Обязательные security/analytics boundaries:
            region_id
            district_id

        Одна SQL-строка:
            school_id + checkpoint
        """

        stmt = (
            select(
                AssessmentQualitySummary
                .school_id
                .label(
                    "entity_id"
                ),

                AssessmentQualitySummary
                .checkpoint_snapshot
                .label(
                    "checkpoint"
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

                AssessmentQualitySummary
                .district_id_snapshot
                == district_id,

                AssessmentQualitySummary
                .academic_year_start_snapshot
                == academic_year_start,

                AssessmentQualitySummary
                .checkpoint_snapshot
                .is_not(None),
            )
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
                AssessmentQualitySummary.school_id,

                AssessmentQualitySummary
                .checkpoint_snapshot,
            )
            .order_by(
                AssessmentQualitySummary.school_id.asc(),

                AssessmentQualitySummary
                .checkpoint_snapshot
                .asc(),
            )
        )

        rows = (
            await db.execute(
                stmt
            )
        ).all()

        return [
            cls._row_to_entity_dynamics(
                row
            )
            for row in rows
        ]
