# app/modules/assessment/services/knowledge_quality_export_service.py

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.repositories.knowledge_quality_analytics_repo import (
    KnowledgeQualityAnalyticsRepo,
)
from app.modules.assessment.schemas.knowledge_quality_export_schemas import (
    KnowledgeQualityExportDTO,
    KnowledgeQualityExportRowDTO,
    KnowledgeQualityExportSummaryDTO,
)
from app.modules.assessment.services.knowledge_quality_analytics_service import (
    KnowledgeQualityAnalyticsService,
)
from app.modules.education.repositories.subject_repo import (
    SubjectRepo,
)
from app.modules.org.repositories.org_lookup_repo import (
    OrgLookupRepo,
)
from app.modules.staff.staff_repo import SchoolStaffRepo


class KnowledgeQualityExportService:
    """
    Подготовка унифицированных данных
    для экспорта аналитики качества знаний.

    Поддерживаемые уровни:
        school
        district
        region

    Service не создаёт Excel/PDF.

    Его задача:
        Analytics DTO
            ->
        KnowledgeQualityExportDTO
            ->
        Excel / PDF / другие форматы

    Все математические показатели уже рассчитаны
    KnowledgeQualityAnalyticsService через
    KnowledgeQualityCalculator.
    """

    # =====================================================
    # SCHOOL
    # =====================================================

    @classmethod
    async def build_school_export(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
        academic_year_start: int | None = None,
        subject_id: int | None = None,
        grade_level: int | None = None,
        work_key: str | None = None,
    ) -> KnowledgeQualityExportDTO:
        """
        Подготовить export DTO школы.

        summary:
            общий итог школы.

        rows:
            классы школы.
        """

        # =================================================
        # SUMMARY
        # =================================================

        analytics = (
            await KnowledgeQualityAnalyticsService
            .get_school_analytics(
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

        # =================================================
        # SCHOOL -> CLASSES
        # =================================================

        class_analytics = (
            await KnowledgeQualityAnalyticsService
            .get_school_class_analytics(
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

        # =================================================
        # CLASS -> TEACHERS
        # =================================================

        teachers_by_class = (
            await KnowledgeQualityAnalyticsRepo
            .get_school_class_teacher_names(
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

        # =================================================
        # ORGANIZATION
        # =================================================

        school_names = (
            await OrgLookupRepo
            .get_school_names_by_ids(
                db,
                school_ids=(
                    school_id,
                ),
            )
        )

        organization_name = (
            school_names.get(
                school_id,
                f"ID {school_id}",
            )
        )

        # =================================================
        # SUBJECT
        # =================================================

        subject_name = (
            await cls._resolve_subject_name(
                db,
                subject_id=subject_id,
            )
        )

        # =================================================
        # ROWS
        # =================================================

        rows = tuple(
            KnowledgeQualityExportRowDTO(
                entity_id=(
                    item.school_class_id
                ),

                entity_name=(
                    item.class_name
                ),

                teacher_names=(
                    teachers_by_class.get(
                        item.school_class_id,
                        (),
                    )
                ),

                total_students=(
                    item.total_students
                ),

                participated_students=(
                    item.participated_students
                ),

                absent_students=(
                    item.absent_students
                ),

                excused_students=(
                    item.excused_students
                ),

                not_completed_students=(
                    item.not_completed_students
                ),

                grade_5_count=(
                    item.grade_5_count
                ),

                grade_4_count=(
                    item.grade_4_count
                ),

                grade_3_count=(
                    item.grade_3_count
                ),

                grade_2_count=(
                    item.grade_2_count
                ),

                average_score=(
                    item.average_score
                ),

                average_percent=(
                    item.average_percent
                ),

                achievement_percent=(
                    item.achievement_percent
                ),

                quality_percent=(
                    item.quality_percent
                ),
            )
            for item in class_analytics.items
        )

        return KnowledgeQualityExportDTO(
            scope="school",

            title=(
                "Мектеп бойынша білім сапасының "
                "аналитикасы"
            ),

            organization_id=school_id,
            organization_name=(
                organization_name
            ),

            academic_year_start=(
                academic_year_start
            ),

            subject_id=subject_id,
            subject_name=subject_name,

            grade_level=grade_level,

            summary=(
                cls._build_summary(
                    analytics
                )
            ),

            rows=rows,
        )

    # =====================================================
    # TEACHER
    # =====================================================

    @classmethod
    async def build_teacher_export(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            work_key: str | None = None,
    ) -> KnowledgeQualityExportDTO:
        """
        Подготовить export DTO текущего учителя.

        summary:
            общий итог учителя.

        rows:
            классы учителя.

        Metadata:
            школа;
            учитель;
            учебный год;
            предмет;
            параллель.

        Security boundary:
            school_id
            teacher_staff_member_id

        teacher_staff_member_id никогда
        не должен приниматься из query params.
        """

        # =====================================================
        # VALIDATION
        # =====================================================

        if school_id <= 0:
            raise ValueError(
                "Некорректный school_id."
            )

        if teacher_staff_member_id <= 0:
            raise ValueError(
                "Некорректный teacher_staff_member_id."
            )

        # =====================================================
        # TEACHER
        # =====================================================

        teacher = (
            await SchoolStaffRepo.get_member(
                db,
                school_id=school_id,
                member_id=(
                    teacher_staff_member_id
                ),
                include_inactive=False,
            )
        )

        if teacher is None:
            raise ValueError(
                "Учитель не найден "
                "в указанной школе "
                "или сотрудник неактивен."
            )

        teacher_name = (
            teacher.full_name.strip()
            if teacher.full_name
            else f"ID {teacher_staff_member_id}"
        )

        # =====================================================
        # SUMMARY
        # =====================================================

        analytics = (
            await KnowledgeQualityAnalyticsService
            .get_teacher_analytics(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
                academic_year_start=(
                    academic_year_start
                ),
                subject_id=(
                    subject_id
                ),
                grade_level=(
                    grade_level
                ),
                work_key=work_key,
            )
        )

        # =====================================================
        # TEACHER -> CLASSES
        # =====================================================

        class_analytics = (
            await KnowledgeQualityAnalyticsService
            .get_teacher_class_analytics(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
                academic_year_start=(
                    academic_year_start
                ),
                subject_id=(
                    subject_id
                ),
                grade_level=(
                    grade_level
                ),
                work_key=work_key,
            )
        )

        # =====================================================
        # SCHOOL
        # =====================================================

        school_names = (
            await OrgLookupRepo
            .get_school_names_by_ids(
                db,
                school_ids=(
                    school_id,
                ),
            )
        )

        school_name = (
            school_names.get(
                school_id,
                f"ID {school_id}",
            )
        )

        # =====================================================
        # SUBJECT
        # =====================================================

        subject_name = (
            await cls._resolve_subject_name(
                db,
                subject_id=subject_id,
            )
        )

        # =====================================================
        # ROWS
        # =====================================================

        rows = tuple(
            KnowledgeQualityExportRowDTO(
                entity_id=(
                    item.school_class_id
                ),

                entity_name=(
                    item.class_name
                ),

                total_students=(
                    item.total_students
                ),

                participated_students=(
                    item.participated_students
                ),

                absent_students=(
                    item.absent_students
                ),

                excused_students=(
                    item.excused_students
                ),

                not_completed_students=(
                    item.not_completed_students
                ),

                grade_5_count=(
                    item.grade_5_count
                ),

                grade_4_count=(
                    item.grade_4_count
                ),

                grade_3_count=(
                    item.grade_3_count
                ),

                grade_2_count=(
                    item.grade_2_count
                ),

                average_score=(
                    item.average_score
                ),

                average_percent=(
                    item.average_percent
                ),

                achievement_percent=(
                    item.achievement_percent
                ),

                quality_percent=(
                    item.quality_percent
                ),
            )
            for item in class_analytics.items
        )

        # =====================================================
        # DTO
        # =====================================================

        return KnowledgeQualityExportDTO(
            scope="teacher",

            title=(
                "Мұғалім бойынша білім сапасының "
                "аналитикасы"
            ),

            # -------------------------------------------------
            # SCHOOL
            # -------------------------------------------------

            organization_id=(
                school_id
            ),

            organization_name=(
                school_name
            ),

            # -------------------------------------------------
            # TEACHER
            # -------------------------------------------------

            teacher_staff_member_id=(
                teacher_staff_member_id
            ),

            teacher_name=(
                teacher_name
            ),

            # -------------------------------------------------
            # FILTERS
            # -------------------------------------------------

            academic_year_start=(
                academic_year_start
            ),

            subject_id=(
                subject_id
            ),

            subject_name=(
                subject_name
            ),

            grade_level=(
                grade_level
            ),

            # -------------------------------------------------
            # ANALYTICS
            # -------------------------------------------------

            summary=(
                cls._build_summary(
                    analytics
                )
            ),

            rows=(
                rows
            ),
        )

    # =====================================================
    # DISTRICT
    # =====================================================

    @classmethod
    async def build_district_export(
        cls,
        db: AsyncSession,
        *,
        district_id: int,
        academic_year_start: int | None = None,
        subject_id: int | None = None,
        grade_level: int | None = None,
        work_key: str | None = None,
    ) -> KnowledgeQualityExportDTO:
        """
        Подготовить export DTO района.

        summary:
            общий итог района.

        rows:
            школы района.
        """

        # =================================================
        # SUMMARY
        # =================================================

        analytics = (
            await KnowledgeQualityAnalyticsService
            .get_district_analytics(
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

        # =================================================
        # DISTRICT -> SCHOOLS
        # =================================================

        school_analytics = (
            await KnowledgeQualityAnalyticsService
            .get_district_school_analytics(
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

        # =================================================
        # ORGANIZATION
        # =================================================

        district_names = (
            await OrgLookupRepo
            .get_district_names_by_ids(
                db,
                district_ids=(
                    district_id,
                ),
            )
        )

        organization_name = (
            district_names.get(
                district_id,
                f"ID {district_id}",
            )
        )

        # =================================================
        # SUBJECT
        # =================================================

        subject_name = (
            await cls._resolve_subject_name(
                db,
                subject_id=subject_id,
            )
        )

        # =================================================
        # ROWS
        # =================================================

        rows = tuple(
            cls._build_drill_down_row(
                item
            )
            for item in school_analytics.items
        )

        return KnowledgeQualityExportDTO(
            scope="district",

            title=(
                "Аудан бойынша білім сапасының "
                "аналитикасы"
            ),

            organization_id=district_id,
            organization_name=(
                organization_name
            ),

            academic_year_start=(
                academic_year_start
            ),

            subject_id=subject_id,
            subject_name=subject_name,

            grade_level=grade_level,

            summary=(
                cls._build_summary(
                    analytics
                )
            ),

            rows=rows,
        )

    # =====================================================
    # REGION
    # =====================================================

    @classmethod
    async def build_region_export(cls, db: AsyncSession, *, region_id: int,
                                  academic_year_start: int | None=None, subject_id: int | None=None,
                                  grade_level: int | None=None, work_key: str | None=None,
                                  governance: str='', checkpoint: str='') -> KnowledgeQualityExportDTO:
        """Prepare the five regional sheets from one filtered school cohort."""
        from app.modules.assessment.services.regional_export_service import build
        return await build(db, region_id=region_id, academic_year_start=academic_year_start,
                           subject_id=subject_id, grade_level=grade_level, work_key=work_key,
                           governance=governance, checkpoint=checkpoint)

    # =====================================================
    # SUMMARY BUILDER
    # =====================================================

    @staticmethod
    def _build_summary(
        analytics,
    ) -> KnowledgeQualityExportSummaryDTO:
        """
        Унифицировать общий аналитический DTO
        в export-summary.
        """

        return KnowledgeQualityExportSummaryDTO(
            total_students=(
                analytics.total_students
            ),

            participated_students=(
                analytics.participated_students
            ),

            absent_students=(
                analytics.absent_students
            ),

            excused_students=(
                analytics.excused_students
            ),

            not_completed_students=(
                analytics.not_completed_students
            ),

            grade_5_count=(
                analytics.grade_5_count
            ),

            grade_4_count=(
                analytics.grade_4_count
            ),

            grade_3_count=(
                analytics.grade_3_count
            ),

            grade_2_count=(
                analytics.grade_2_count
            ),

            average_score=(
                analytics.average_score
            ),

            average_percent=(
                analytics.average_percent
            ),

            achievement_percent=(
                analytics.achievement_percent
            ),

            quality_percent=(
                analytics.quality_percent
            ),
        )

    # =====================================================
    # DRILL-DOWN ROW BUILDER
    # =====================================================

    @staticmethod
    def _build_drill_down_row(
        item,
    ) -> KnowledgeQualityExportRowDTO:
        """
        Преобразовать районную/региональную
        drill-down строку в export-row.
        """

        return KnowledgeQualityExportRowDTO(
            entity_id=(
                item.entity_id
            ),

            entity_name=(
                item.entity_name
            ),

            total_students=(
                item.total_students
            ),

            participated_students=(
                item.participated_students
            ),

            absent_students=(
                item.absent_students
            ),

            excused_students=(
                item.excused_students
            ),

            not_completed_students=(
                item.not_completed_students
            ),

            grade_5_count=(
                item.grade_5_count
            ),

            grade_4_count=(
                item.grade_4_count
            ),

            grade_3_count=(
                item.grade_3_count
            ),

            grade_2_count=(
                item.grade_2_count
            ),

            average_score=(
                item.average_score
            ),

            average_percent=(
                item.average_percent
            ),

            achievement_percent=(
                item.achievement_percent
            ),

            quality_percent=(
                item.quality_percent
            ),
        )

    # =====================================================
    # SUBJECT LOOKUP
    # =====================================================

    @staticmethod
    async def _resolve_subject_name(
        db: AsyncSession,
        *,
        subject_id: int | None,
    ) -> str | None:
        """
        Получить название выбранного предмета.

        None означает:
            все предметы.
        """

        if subject_id is None:
            return None

        subjects = (
            await SubjectRepo.get_active_by_ids(
                db,
                subject_ids=(
                    subject_id,
                ),
            )
        )

        if not subjects:
            return f"ID {subject_id}"

        subject = subjects[0]

        return (
            subject.name_kz
            or f"ID {subject_id}"
        )
