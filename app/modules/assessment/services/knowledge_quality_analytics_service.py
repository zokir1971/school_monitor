# app/modules/assessment/services/knowledge_quality_analytics_service.py

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.repositories.knowledge_quality_analytics_repo import (
    KnowledgeQualityAggregateRow,
    KnowledgeQualityAnalyticsRepo, KnowledgeQualityFilterOptionsRow,
)
from app.modules.assessment.schemas.knowledge_quality_analytics_schemas import (
    KnowledgeQualityAnalyticsDTO, KnowledgeQualityDrillDownDTO, KnowledgeQualityDrillDownItemDTO,
    KnowledgeQualitySchoolClassesDTO, KnowledgeQualitySchoolClassItemDTO,
)
from app.modules.assessment.services.knowledge_quality_calculator import (
    KnowledgeQualityCalculator,
)
from app.modules.org.repositories.org_lookup_repo import OrgLookupRepo


class KnowledgeQualityAnalyticsService:
    """
    Агрегированная аналитика качества знаний.

    Уровни:
        - school;
        - district;
        - region.

    Не загружает AssessmentStudent / AssessmentResult.
    Работает исключительно через AssessmentQualitySummary.
    """

    # =====================================================
    # SCHOOL
    # =====================================================
    @classmethod
    async def get_all_work_rows(cls, db, *, scope, scope_id, teacher_staff_member_id=None,
                                academic_year_start=None, subject_id=None, grade_level=None,
                                checkpoint='', offset=0, limit=51):
        from app.modules.assessment.schemas.knowledge_quality_export_schemas import KnowledgeQualityExportRowDTO
        from app.core.ui_locale_context import ui_locale
        rows = await KnowledgeQualityAnalyticsRepo.get_all_work_rows(
            db, scope=scope, scope_id=scope_id, teacher_staff_member_id=teacher_staff_member_id,
            academic_year_start=academic_year_start, subject_id=subject_id, grade_level=grade_level,
            checkpoint=checkpoint, offset=offset, limit=limit)
        ids = tuple({row['entity_id'] for row in rows})
        names = (await OrgLookupRepo.get_school_names_by_ids(db, school_ids=ids)) if scope == 'district' and ids else (
            await OrgLookupRepo.get_district_names_by_ids(db, district_ids=ids)) if scope == 'region' and ids else {}
        counts = ('total_students','participated_students','absent_students','excused_students',
                  'not_completed_students','grade_5_count','grade_4_count','grade_3_count','grade_2_count')
        result = []
        kk = ui_locale.get() == 'kk'
        for row in rows:
            values = {key:int(row[key] or 0) for key in counts}
            metrics = KnowledgeQualityCalculator.calculate(**values,
                score_sum=row['score_sum'], percent_sum=row['percent_sum'])
            number = int(row['logical_id'])
            suffix = ('Сессия №' + str(row['session_id'])) if number > 0 else (('Жұмыс №' if kk else 'Работа №') + str(-number))
            labels = {
                'baseline':('Нулевой контроль','Нөлдік бақылау'),
                'quarter_1':('I четверть','I тоқсан'), 'quarter_2':('II четверть','II тоқсан'),
                'quarter_3':('III четверть','III тоқсан'), 'quarter_4':('IV четверть','IV тоқсан'),
                'final':('Годовой контроль','Жылдық бақылау'),
            }
            label = labels.get(row['checkpoint'])
            result.append(KnowledgeQualityExportRowDTO(**values, entity_id=row['entity_id'],
                work_key=('d:' + str(number)) if number > 0 else ('a:' + str(-number)),
                score_sum=row['score_sum'], percent_sum=row['percent_sum'],
                full_work_title=(row['work_title'] or '—') + ' · ' + suffix,
                entity_name=(row['class_name'] or '—') if scope in ('school','teacher') else names.get(row['entity_id'], str(row['entity_id'])),
                work_title=label[1 if kk else 0] if label else (row['work_title'] or '—') + ' · ' + suffix,
                average_score=metrics.average_score, average_percent=metrics.average_percent,
                achievement_percent=metrics.achievement_percent, quality_percent=metrics.quality_percent))
        return tuple(result)

    @staticmethod
    def summarize_work_rows(rows):
        """One summary per logical work; use raw sums, never rounded averages."""
        from collections import defaultdict
        from decimal import Decimal
        from dataclasses import replace
        grouped = defaultdict(list)
        for row in rows:grouped[row.work_key].append(row)
        result = []
        counts = ('total_students','participated_students','absent_students','excused_students',
                  'not_completed_students','grade_5_count','grade_4_count','grade_3_count','grade_2_count')
        for key, items in grouped.items():
            values = {name:sum(getattr(row,name) for row in items) for name in counts}
            score_sum = sum((row.score_sum for row in items), Decimal(0))
            percent_sum = sum((row.percent_sum for row in items), Decimal(0))
            metrics = KnowledgeQualityCalculator.calculate(**values, score_sum=score_sum, percent_sum=percent_sum)
            result.append(replace(items[0], **values, entity_id=0,
                entity_name=str(len({row.entity_id for row in items})), score_sum=score_sum, percent_sum=percent_sum,
                average_score=metrics.average_score, average_percent=metrics.average_percent,
                achievement_percent=metrics.achievement_percent, quality_percent=metrics.quality_percent))
        return tuple(result)

    @classmethod
    async def get_school_filter_options(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
    ) -> KnowledgeQualityFilterOptionsRow:
        """
        Доступные фильтры аналитики школы.

        Источник:
            AssessmentQualitySummary

        Возвращает только те значения,
        по которым существуют аналитические
        snapshot-строки текущей школы.
        """

        if school_id <= 0:
            raise ValueError(
                "Некорректный school_id."
            )

        return (
            await KnowledgeQualityAnalyticsRepo
            .get_school_filter_options(
                db,
                school_id=school_id,
            )
        )

    @classmethod
    async def get_school_analytics(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
        academic_year_start: int | None = None,
        subject_id: int | None = None,
        grade_level: int | None = None,
        work_key: str | None = None,
    ) -> KnowledgeQualityAnalyticsDTO:
        row = (
            await KnowledgeQualityAnalyticsRepo
            .get_school_summary(
                db,
                school_id=school_id,
                academic_year_start=academic_year_start,
                subject_id=subject_id,
                grade_level=grade_level,
                work_key=work_key,
            )
        )

        return cls._build_dto(
            row=row,

            scope="school",

            school_id=school_id,
            district_id=None,
            region_id=None,

            academic_year_start=academic_year_start,
            subject_id=subject_id,
            grade_level=grade_level,
        )

    # =====================================================
    # DISTRICT
    # =====================================================

    @classmethod
    async def get_district_analytics(
        cls,
        db: AsyncSession,
        *,
        district_id: int,
        academic_year_start: int | None = None,
        subject_id: int | None = None,
        grade_level: int | None = None,
        school_id: int | None = None,
        work_key: str | None = None,
    ) -> KnowledgeQualityAnalyticsDTO:
        row = (
            await KnowledgeQualityAnalyticsRepo
            .get_district_summary(
                db,
                district_id=district_id,
                academic_year_start=academic_year_start,
                subject_id=subject_id,
                grade_level=grade_level,
                school_id=school_id,
                work_key=work_key,
            )
        )

        return cls._build_dto(
            row=row,

            scope="district",

            school_id=school_id,
            district_id=district_id,
            region_id=None,

            academic_year_start=academic_year_start,
            subject_id=subject_id,
            grade_level=grade_level,
        )

    # =====================================================
    # REGION
    # =====================================================

    @classmethod
    async def get_region_analytics(
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
    ) -> KnowledgeQualityAnalyticsDTO:
        row = (
            await KnowledgeQualityAnalyticsRepo
            .get_region_summary(
                db,
                region_id=region_id,
                academic_year_start=academic_year_start,
                subject_id=subject_id,
                grade_level=grade_level,
                district_id=district_id,
                school_id=school_id,
                work_key=work_key,
            )
        )

        return cls._build_dto(
            row=row,

            scope="region",

            school_id=school_id,
            district_id=district_id,
            region_id=region_id,

            academic_year_start=academic_year_start,
            subject_id=subject_id,
            grade_level=grade_level,
        )

    # =====================================================
    # DTO BUILDER
    # =====================================================

    @staticmethod
    def _build_dto(
        *,
        row: KnowledgeQualityAggregateRow,

        scope: str,

        school_id: int | None,
        district_id: int | None,
        region_id: int | None,

        academic_year_start: int | None,
        subject_id: int | None,
        grade_level: int | None,
    ) -> KnowledgeQualityAnalyticsDTO:
        metrics = (
            KnowledgeQualityCalculator.calculate(
                total_students=(
                    row.total_students
                ),

                participated_students=(
                    row.participated_students
                ),

                absent_students=(
                    row.absent_students
                ),

                excused_students=(
                    row.excused_students
                ),

                not_completed_students=(
                    row.not_completed_students
                ),

                grade_5_count=(
                    row.grade_5_count
                ),

                grade_4_count=(
                    row.grade_4_count
                ),

                grade_3_count=(
                    row.grade_3_count
                ),

                grade_2_count=(
                    row.grade_2_count
                ),

                score_sum=(
                    row.score_sum
                ),

                percent_sum=(
                    row.percent_sum
                ),
            )
        )

        return KnowledgeQualityAnalyticsDTO(
            scope=scope,

            school_id=school_id,
            district_id=district_id,
            region_id=region_id,

            academic_year_start=(
                academic_year_start
            ),

            subject_id=subject_id,
            grade_level=grade_level,

            total_students=(
                row.total_students
            ),

            participated_students=(
                row.participated_students
            ),

            absent_students=(
                row.absent_students
            ),

            excused_students=(
                row.excused_students
            ),

            not_completed_students=(
                row.not_completed_students
            ),

            grade_5_count=(
                row.grade_5_count
            ),

            grade_4_count=(
                row.grade_4_count
            ),

            grade_3_count=(
                row.grade_3_count
            ),

            grade_2_count=(
                row.grade_2_count
            ),

            score_sum=(
                row.score_sum
            ),

            percent_sum=(
                row.percent_sum
            ),

            average_score=(
                metrics.average_score
            ),

            average_percent=(
                metrics.average_percent
            ),

            achievement_percent=(
                metrics.achievement_percent
            ),

            quality_percent=(
                metrics.quality_percent
            ),
        )

    @classmethod
    def _build_drill_down_items(
            cls,
            *,
            rows,
            names: dict[int, str],
    ) -> tuple[
        KnowledgeQualityDrillDownItemDTO,
        ...
    ]:
        items: list[
            KnowledgeQualityDrillDownItemDTO
        ] = []

        for row in rows:
            metrics = (
                KnowledgeQualityCalculator.calculate(
                    total_students=(
                        row.total_students
                    ),
                    participated_students=(
                        row.participated_students
                    ),

                    absent_students=(
                        row.absent_students
                    ),
                    excused_students=(
                        row.excused_students
                    ),
                    not_completed_students=(
                        row.not_completed_students
                    ),

                    grade_5_count=(
                        row.grade_5_count
                    ),
                    grade_4_count=(
                        row.grade_4_count
                    ),
                    grade_3_count=(
                        row.grade_3_count
                    ),
                    grade_2_count=(
                        row.grade_2_count
                    ),

                    score_sum=(
                        row.score_sum
                    ),
                    percent_sum=(
                        row.percent_sum
                    ),
                )
            )

            items.append(
                KnowledgeQualityDrillDownItemDTO(
                    entity_id=(
                        row.entity_id
                    ),

                    entity_name=(
                        names.get(
                            row.entity_id,
                            f"ID {row.entity_id}",
                        )
                    ),

                    total_students=(
                        row.total_students
                    ),
                    participated_students=(
                        row.participated_students
                    ),

                    absent_students=(
                        row.absent_students
                    ),
                    excused_students=(
                        row.excused_students
                    ),
                    not_completed_students=(
                        row.not_completed_students
                    ),

                    grade_5_count=(
                        row.grade_5_count
                    ),
                    grade_4_count=(
                        row.grade_4_count
                    ),
                    grade_3_count=(
                        row.grade_3_count
                    ),
                    grade_2_count=(
                        row.grade_2_count
                    ),

                    score_sum=(
                        row.score_sum
                    ),
                    percent_sum=(
                        row.percent_sum
                    ),

                    average_score=(
                        metrics.average_score
                    ),
                    average_percent=(
                        metrics.average_percent
                    ),

                    achievement_percent=(
                        metrics.achievement_percent
                    ),
                    quality_percent=(
                        metrics.quality_percent
                    ),
                )
            )

        return tuple(
            items
        )

    @classmethod
    async def get_district_school_analytics(
            cls,
            db: AsyncSession,
            *,
            district_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            work_key: str | None = None,
    ) -> KnowledgeQualityDrillDownDTO:
        """
        Drill-down района по школам.
        """

        rows = (
            await KnowledgeQualityAnalyticsRepo
            .get_district_school_rows(
                db,
                district_id=district_id,
                academic_year_start=(
                    academic_year_start
                ),
                subject_id=subject_id,
                grade_level=grade_level,
                work_key=work_key,
            )
        )

        school_ids = tuple(
            row.entity_id
            for row in rows
        )

        school_names = (
            await OrgLookupRepo
            .get_school_names_by_ids(
                db,
                school_ids=school_ids,
            )
        )

        items = cls._build_drill_down_items(
            rows=rows,
            names=school_names,
        )

        return KnowledgeQualityDrillDownDTO(
            scope="district_schools",
            parent_id=district_id,

            academic_year_start=(
                academic_year_start
            ),
            subject_id=subject_id,
            grade_level=grade_level,

            items=items,
        )

    @classmethod
    async def get_region_district_analytics(
            cls,
            db: AsyncSession,
            *,
            region_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            work_key: str | None = None,
    ) -> KnowledgeQualityDrillDownDTO:
        """
        Drill-down региона по районам.
        """

        rows = (
            await KnowledgeQualityAnalyticsRepo
            .get_region_district_rows(
                db,
                region_id=region_id,
                academic_year_start=(
                    academic_year_start
                ),
                subject_id=subject_id,
                grade_level=grade_level,
                work_key=work_key,
            )
        )

        district_ids = tuple(
            row.entity_id
            for row in rows
        )

        district_names = (
            await OrgLookupRepo
            .get_district_names_by_ids(
                db,
                district_ids=district_ids,
            )
        )

        items = cls._build_drill_down_items(
            rows=rows,
            names=district_names,
        )

        return KnowledgeQualityDrillDownDTO(
            scope="region_districts",
            parent_id=region_id,

            academic_year_start=(
                academic_year_start
            ),
            subject_id=subject_id,
            grade_level=grade_level,

            items=items,
        )

    @classmethod
    async def get_school_class_analytics(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            work_key: str | None = None,
    ) -> KnowledgeQualitySchoolClassesDTO:
        rows = (
            await KnowledgeQualityAnalyticsRepo
            .get_school_class_rows(
                db,
                school_id=school_id,
                academic_year_start=(
                    academic_year_start
                ),
                subject_id=subject_id,
                grade_level=grade_level,
                work_key=work_key,
            )
        )

        items: list[
            KnowledgeQualitySchoolClassItemDTO
        ] = []

        for row in rows:
            metrics = (
                KnowledgeQualityCalculator.calculate(
                    total_students=(
                        row.total_students
                    ),

                    participated_students=(
                        row.participated_students
                    ),

                    absent_students=(
                        row.absent_students
                    ),

                    excused_students=(
                        row.excused_students
                    ),

                    not_completed_students=(
                        row.not_completed_students
                    ),

                    grade_5_count=(
                        row.grade_5_count
                    ),

                    grade_4_count=(
                        row.grade_4_count
                    ),

                    grade_3_count=(
                        row.grade_3_count
                    ),

                    grade_2_count=(
                        row.grade_2_count
                    ),

                    score_sum=(
                        row.score_sum
                    ),

                    percent_sum=(
                        row.percent_sum
                    ),
                )
            )

            items.append(
                KnowledgeQualitySchoolClassItemDTO(
                    school_class_id=(
                        row.school_class_id
                    ),

                    class_name=(
                        row.class_name
                    ),

                    grade_level=(
                        row.grade_level
                    ),

                    total_students=(
                        row.total_students
                    ),

                    participated_students=(
                        row.participated_students
                    ),

                    absent_students=(
                        row.absent_students
                    ),

                    excused_students=(
                        row.excused_students
                    ),

                    not_completed_students=(
                        row.not_completed_students
                    ),

                    grade_5_count=(
                        row.grade_5_count
                    ),

                    grade_4_count=(
                        row.grade_4_count
                    ),

                    grade_3_count=(
                        row.grade_3_count
                    ),

                    grade_2_count=(
                        row.grade_2_count
                    ),

                    average_score=(
                        metrics.average_score
                    ),

                    average_percent=(
                        metrics.average_percent
                    ),

                    achievement_percent=(
                        metrics.achievement_percent
                    ),

                    quality_percent=(
                        metrics.quality_percent
                    ),
                )
            )

        return KnowledgeQualitySchoolClassesDTO(
            school_id=school_id,

            academic_year_start=(
                academic_year_start
            ),

            subject_id=subject_id,
            grade_level=grade_level,

            items=tuple(
                items
            ),
        )

    # =====================================================
    # TEACHER
    # =====================================================

    @classmethod
    async def get_teacher_analytics(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            work_key: str | None = None,
    ) -> KnowledgeQualityAnalyticsDTO:
        """
        Общая аналитика конкретного учителя.

        Использует только AssessmentQualitySummary.
        """

        row = (
            await KnowledgeQualityAnalyticsRepo
            .get_teacher_summary(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
                academic_year_start=(
                    academic_year_start
                ),
                subject_id=subject_id,
                grade_level=grade_level,
                work_key=work_key,
            )
        )

        return cls._build_dto(
            row=row,

            scope="teacher",

            school_id=school_id,
            district_id=None,
            region_id=None,

            academic_year_start=(
                academic_year_start
            ),
            subject_id=subject_id,
            grade_level=grade_level,
        )

    @classmethod
    async def get_teacher_class_analytics(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            work_key: str | None = None,
    ) -> KnowledgeQualitySchoolClassesDTO:
        """
        Аналитика учителя по его классам.
        """

        rows = (
            await KnowledgeQualityAnalyticsRepo
            .get_teacher_class_rows(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
                academic_year_start=(
                    academic_year_start
                ),
                subject_id=subject_id,
                grade_level=grade_level,
                work_key=work_key,
            )
        )

        items: list[
            KnowledgeQualitySchoolClassItemDTO
        ] = []

        for row in rows:
            metrics = (
                KnowledgeQualityCalculator.calculate(
                    total_students=(
                        row.total_students
                    ),

                    participated_students=(
                        row.participated_students
                    ),

                    absent_students=(
                        row.absent_students
                    ),

                    excused_students=(
                        row.excused_students
                    ),

                    not_completed_students=(
                        row.not_completed_students
                    ),

                    grade_5_count=(
                        row.grade_5_count
                    ),

                    grade_4_count=(
                        row.grade_4_count
                    ),

                    grade_3_count=(
                        row.grade_3_count
                    ),

                    grade_2_count=(
                        row.grade_2_count
                    ),

                    score_sum=(
                        row.score_sum
                    ),

                    percent_sum=(
                        row.percent_sum
                    ),
                )
            )

            items.append(
                KnowledgeQualitySchoolClassItemDTO(
                    school_class_id=(
                        row.school_class_id
                    ),

                    class_name=(
                        row.class_name
                    ),

                    grade_level=(
                        row.grade_level
                    ),

                    total_students=(
                        row.total_students
                    ),

                    participated_students=(
                        row.participated_students
                    ),

                    absent_students=(
                        row.absent_students
                    ),

                    excused_students=(
                        row.excused_students
                    ),

                    not_completed_students=(
                        row.not_completed_students
                    ),

                    grade_5_count=(
                        row.grade_5_count
                    ),

                    grade_4_count=(
                        row.grade_4_count
                    ),

                    grade_3_count=(
                        row.grade_3_count
                    ),

                    grade_2_count=(
                        row.grade_2_count
                    ),

                    average_score=(
                        metrics.average_score
                    ),

                    average_percent=(
                        metrics.average_percent
                    ),

                    achievement_percent=(
                        metrics.achievement_percent
                    ),

                    quality_percent=(
                        metrics.quality_percent
                    ),
                )
            )

        return KnowledgeQualitySchoolClassesDTO(
            school_id=school_id,

            academic_year_start=(
                academic_year_start
            ),

            subject_id=subject_id,
            grade_level=grade_level,

            items=tuple(
                items
            ),
        )
