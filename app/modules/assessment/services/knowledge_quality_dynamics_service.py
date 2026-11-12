# app/modules/assessment/services/knowledge_quality_dynamics_service.py

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.enums import (
    AssessmentCheckpoint,
)
from app.modules.assessment.repositories.knowledge_quality_dynamics_repo import (
    KnowledgeQualityDynamicsRepo,
    KnowledgeQualityDynamicsRow,
    KnowledgeQualityEntityDynamicsRow,
)
from app.modules.assessment.schemas.knowledge_quality_dynamics_schemas import (
    KnowledgeQualityCheckpointDTO,
    KnowledgeQualityDynamicsDTO,
    KnowledgeQualityEntityDynamicsDTO,
    KnowledgeQualityEntityDynamicsItemDTO,
)
from app.modules.assessment.schemas.knowledge_quality_dynamics_schemas import (
    KnowledgeQualityDynamicsFilterOptionsDTO,
)
from app.modules.education.repositories.school_class_repo import (
    SchoolClassRepo,
)
from app.modules.org.repositories.org_lookup_repo import (
    OrgLookupRepo,
)


class KnowledgeQualityDynamicsService:
    """
    Сервис динамики качества знаний
    внутри одного учебного года.

    Источник данных:
        AssessmentQualitySummary
            ->
        KnowledgeQualityDynamicsRepo

    Service Layer отвечает за:
        - бизнес-порядок контрольных точек;
        - расчёт качества знаний;
        - расчёт delta vs previous;
        - расчёт delta vs baseline;
        - построение DTO;
        - batch-разрешение названий школ / районов.

    Service не:
        - читает AssessmentStudent;
        - читает AssessmentResult;
        - выполняет SQL внутри циклов;
        - выполняет commit.

    Динамика рассчитывается в процентных пунктах.
    """

    HUNDRED = Decimal("100")
    PERCENT_QUANT = Decimal("0.01")
    ZERO = Decimal("0.00")

    # =====================================================
    # CHECKPOINT ORDER
    # =====================================================

    CHECKPOINT_ORDER: tuple[
        AssessmentCheckpoint,
        ...
    ] = (
        AssessmentCheckpoint.BASELINE,
        AssessmentCheckpoint.QUARTER_1,
        AssessmentCheckpoint.QUARTER_2,
        AssessmentCheckpoint.QUARTER_3,
        AssessmentCheckpoint.QUARTER_4,
        AssessmentCheckpoint.FINAL,
    )

    CHECKPOINT_POSITION: dict[
        AssessmentCheckpoint,
        int,
    ] = {
        checkpoint: position
        for position, checkpoint
        in enumerate(
            CHECKPOINT_ORDER
        )
    }

    # =====================================================
    # SCHOOL
    # =====================================================

    @classmethod
    async def get_school_filter_options(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
    ) -> KnowledgeQualityDynamicsFilterOptionsDTO:
        """
        Каскадные фильтры школьной страницы динамики.

        Источник filter options:
            только AssessmentQualitySummary с
            checkpoint_snapshot IS NOT NULL.

        SQL:
            1 запрос — все уникальные комбинации
            year + subject + grade.

        Нормализация:
            1. Если год не передан — выбирается самый новый.
            2. Некорректный / недоступный subject -> None.
            3. Некорректный / недоступный grade -> None.
            4. subject options зависят от выбранного года.
            5. grade options зависят от выбранного года
               и выбранного subject, если он выбран.
        """

        cls._validate_positive_id(
            "school_id",
            school_id,
        )

        rows = (
            await KnowledgeQualityDynamicsRepo
            .get_school_filter_rows(
                db,
                school_id=school_id,
            )
        )

        academic_years = tuple(
            sorted(
                {
                    item.academic_year_start
                    for item in rows
                },
                reverse=True,
            )
        )

        if not academic_years:
            return KnowledgeQualityDynamicsFilterOptionsDTO(
                academic_years=(),
                subject_ids=(),
                grade_levels=(),
                selected_academic_year=None,
                selected_subject_id=None,
                selected_grade_level=None,
            )

        selected_academic_year = (
            academic_year_start
            if academic_year_start in academic_years
            else academic_years[0]
        )

        year_rows = tuple(
            item
            for item in rows
            if (
                item.academic_year_start
                == selected_academic_year
            )
        )

        subject_ids = tuple(
            sorted(
                {
                    item.subject_id
                    for item in year_rows
                }
            )
        )

        selected_subject_id = (
            subject_id
            if subject_id in subject_ids
            else None
        )

        grade_source_rows = (
            tuple(
                item
                for item in year_rows
                if (
                    item.subject_id
                    == selected_subject_id
                )
            )
            if selected_subject_id is not None
            else year_rows
        )

        grade_levels = tuple(
            sorted(
                {
                    item.grade_level
                    for item in grade_source_rows
                }
            )
        )

        selected_grade_level = (
            grade_level
            if grade_level in grade_levels
            else None
        )

        return KnowledgeQualityDynamicsFilterOptionsDTO(
            academic_years=academic_years,
            subject_ids=subject_ids,
            grade_levels=grade_levels,
            selected_academic_year=(
                selected_academic_year
            ),
            selected_subject_id=(
                selected_subject_id
            ),
            selected_grade_level=(
                selected_grade_level
            ),
        )

    @classmethod
    async def get_school_dynamics(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            academic_year_start: int,
            subject_id: int | None = None,
            grade_level: int | None = None,
            school_class_id: int | None = None,
            teacher_staff_member_id: int | None = None,
    ) -> KnowledgeQualityDynamicsDTO:
        """
        Динамика школы.

        Поддерживаемый drill-down:

            school
                -> subject
                -> grade
                -> class
                -> teacher
        """

        cls._validate_positive_id(
            "school_id",
            school_id,
        )

        cls._validate_academic_year(
            academic_year_start
        )

        cls._validate_optional_positive_id(
            "subject_id",
            subject_id,
        )

        cls._validate_optional_positive_id(
            "grade_level",
            grade_level,
        )

        cls._validate_optional_positive_id(
            "school_class_id",
            school_class_id,
        )

        cls._validate_optional_positive_id(
            "teacher_staff_member_id",
            teacher_staff_member_id,
        )

        rows = (
            await KnowledgeQualityDynamicsRepo
            .get_school_checkpoint_rows(
                db,
                school_id=school_id,
                academic_year_start=(
                    academic_year_start
                ),
                subject_id=subject_id,
                grade_level=grade_level,
                school_class_id=(
                    school_class_id
                ),
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
            )
        )

        points = cls._build_checkpoint_points(
            rows
        )

        return KnowledgeQualityDynamicsDTO(
            scope="school",

            academic_year_start=(
                academic_year_start
            ),

            school_id=school_id,
            district_id=None,
            region_id=None,

            subject_id=subject_id,
            grade_level=grade_level,

            school_class_id=(
                school_class_id
            ),

            teacher_staff_member_id=(
                teacher_staff_member_id
            ),

            points=points,
        )

    # =====================================================
    # SCHOOL -> CLASSES
    # =====================================================

    @classmethod
    async def get_school_class_dynamics(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            academic_year_start: int,
            subject_id: int | None = None,
            grade_level: int | None = None,
    ) -> KnowledgeQualityEntityDynamicsDTO:
        """
        Динамика школы с разбивкой по классам.

        SQL:
            1 запрос — все class + checkpoint.

        Затем:
            1 batch-запрос — классы школы за учебный год.

        SQL внутри цикла отсутствует.
        """

        cls._validate_positive_id(
            "school_id",
            school_id,
        )

        cls._validate_academic_year(
            academic_year_start
        )

        cls._validate_optional_positive_id(
            "subject_id",
            subject_id,
        )

        cls._validate_optional_positive_id(
            "grade_level",
            grade_level,
        )

        rows = (
            await KnowledgeQualityDynamicsRepo
            .get_school_class_checkpoint_rows(
                db,
                school_id=school_id,
                academic_year_start=(
                    academic_year_start
                ),
                subject_id=subject_id,
                grade_level=grade_level,
            )
        )

        class_ids = cls._extract_entity_ids(
            rows
        )

        if class_ids:
            school_classes = (
                await SchoolClassRepo
                .get_active_by_school_and_year(
                    db,
                    school_id=school_id,
                    academic_year_start=(
                        academic_year_start
                    ),
                )
            )

            class_names = {
                int(school_class.id): (
                    school_class.name
                )
                for school_class in school_classes
                if school_class.id in class_ids
            }
        else:
            class_names = {}

        items = cls._build_entity_items(
            rows=rows,
            names=class_names,
        )

        return KnowledgeQualityEntityDynamicsDTO(
            scope="school_classes",

            parent_id=school_id,

            academic_year_start=(
                academic_year_start
            ),

            subject_id=subject_id,
            grade_level=grade_level,

            items=items,
        )

    # =====================================================
    # DISTRICT
    # =====================================================

    @classmethod
    async def get_district_filter_options(
            cls,
            db: AsyncSession,
            *,
            district_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
    ) -> KnowledgeQualityDynamicsFilterOptionsDTO:
        """
        Каскадные фильтры районной динамики.

        Источник:
            AssessmentQualitySummary
            только checkpoint_snapshot IS NOT NULL.

        SQL:
            1 запрос на все уникальные
            year + subject + grade района.
        """

        cls._validate_positive_id(
            "district_id",
            district_id,
        )

        rows = (
            await KnowledgeQualityDynamicsRepo
            .get_district_filter_rows(
                db,
                district_id=district_id,
            )
        )

        academic_years = tuple(
            sorted(
                {
                    item.academic_year_start
                    for item in rows
                },
                reverse=True,
            )
        )

        if not academic_years:
            return KnowledgeQualityDynamicsFilterOptionsDTO(
                academic_years=(),
                subject_ids=(),
                grade_levels=(),
                selected_academic_year=None,
                selected_subject_id=None,
                selected_grade_level=None,
            )

        selected_academic_year = (
            academic_year_start
            if academic_year_start in academic_years
            else academic_years[0]
        )

        year_rows = tuple(
            item
            for item in rows
            if (
                    item.academic_year_start
                    == selected_academic_year
            )
        )

        subject_ids = tuple(
            sorted(
                {
                    item.subject_id
                    for item in year_rows
                }
            )
        )

        selected_subject_id = (
            subject_id
            if subject_id in subject_ids
            else None
        )

        grade_source_rows = (
            tuple(
                item
                for item in year_rows
                if (
                        item.subject_id
                        == selected_subject_id
                )
            )
            if selected_subject_id is not None
            else year_rows
        )

        grade_levels = tuple(
            sorted(
                {
                    item.grade_level
                    for item in grade_source_rows
                }
            )
        )

        selected_grade_level = (
            grade_level
            if grade_level in grade_levels
            else None
        )

        return KnowledgeQualityDynamicsFilterOptionsDTO(
            academic_years=academic_years,
            subject_ids=subject_ids,
            grade_levels=grade_levels,

            selected_academic_year=(
                selected_academic_year
            ),

            selected_subject_id=(
                selected_subject_id
            ),

            selected_grade_level=(
                selected_grade_level
            ),
        )

    @classmethod
    async def get_district_dynamics(
            cls,
            db: AsyncSession,
            *,
            district_id: int,
            academic_year_start: int,
            subject_id: int | None = None,
            grade_level: int | None = None,
            school_id: int | None = None,
    ) -> KnowledgeQualityDynamicsDTO:
        """
        Общая динамика района.

        Поддерживаемый drill-down:

            district
                -> subject
                -> grade
                -> school

        Район не получает:
            - class;
            - teacher;
            - student.
        """

        cls._validate_positive_id(
            "district_id",
            district_id,
        )

        cls._validate_academic_year(
            academic_year_start
        )

        cls._validate_optional_positive_id(
            "subject_id",
            subject_id,
        )

        cls._validate_optional_positive_id(
            "grade_level",
            grade_level,
        )

        cls._validate_optional_positive_id(
            "school_id",
            school_id,
        )

        rows = (
            await KnowledgeQualityDynamicsRepo
            .get_district_checkpoint_rows(
                db,
                district_id=district_id,
                academic_year_start=(
                    academic_year_start
                ),
                subject_id=subject_id,
                grade_level=grade_level,
                school_id=school_id,
            )
        )

        points = cls._build_checkpoint_points(
            rows
        )

        return KnowledgeQualityDynamicsDTO(
            scope="district",

            academic_year_start=(
                academic_year_start
            ),

            school_id=school_id,
            district_id=district_id,
            region_id=None,

            subject_id=subject_id,
            grade_level=grade_level,

            school_class_id=None,
            teacher_staff_member_id=None,

            points=points,
        )

    # =====================================================
    # DISTRICT -> SCHOOLS
    # =====================================================

    @classmethod
    async def get_district_school_dynamics(
            cls,
            db: AsyncSession,
            *,
            district_id: int,
            academic_year_start: int,
            subject_id: int | None = None,
            grade_level: int | None = None,
    ) -> KnowledgeQualityEntityDynamicsDTO:
        """
        Динамика района с разбивкой по школам.

        SQL:
            1 запрос — все school + checkpoint.

        Затем:
            1 batch-запрос — названия всех школ.

        SQL внутри цикла отсутствует.
        """

        cls._validate_positive_id(
            "district_id",
            district_id,
        )

        cls._validate_academic_year(
            academic_year_start
        )

        cls._validate_optional_positive_id(
            "subject_id",
            subject_id,
        )

        cls._validate_optional_positive_id(
            "grade_level",
            grade_level,
        )

        rows = (
            await KnowledgeQualityDynamicsRepo
            .get_district_school_checkpoint_rows(
                db,
                district_id=district_id,
                academic_year_start=(
                    academic_year_start
                ),
                subject_id=subject_id,
                grade_level=grade_level,
            )
        )

        school_ids = cls._extract_entity_ids(
            rows
        )

        school_names = (
            await OrgLookupRepo
            .get_school_names_by_ids(
                db,
                school_ids=school_ids,
            )
            if school_ids
            else {}
        )

        items = cls._build_entity_items(
            rows=rows,
            names=school_names,
        )

        return KnowledgeQualityEntityDynamicsDTO(
            scope="district_schools",

            parent_id=district_id,

            academic_year_start=(
                academic_year_start
            ),

            subject_id=subject_id,
            grade_level=grade_level,

            items=items,
        )

    # =====================================================
    # REGION
    # =====================================================

    @classmethod
    async def get_region_filter_options(
            cls,
            db: AsyncSession,
            *,
            region_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
    ) -> KnowledgeQualityDynamicsFilterOptionsDTO:
        """
        Каскадные фильтры региональной страницы динамики.

        Источник:
            только AssessmentQualitySummary,
            где checkpoint_snapshot IS NOT NULL.

        SQL:
            1 запрос на все уникальные
            year + subject + grade региона.
        """

        cls._validate_positive_id(
            "region_id",
            region_id,
        )

        rows = (
            await KnowledgeQualityDynamicsRepo
            .get_region_filter_rows(
                db,
                region_id=region_id,
            )
        )

        academic_years = tuple(
            sorted(
                {
                    item.academic_year_start
                    for item in rows
                },
                reverse=True,
            )
        )

        if not academic_years:
            return KnowledgeQualityDynamicsFilterOptionsDTO(
                academic_years=(),
                subject_ids=(),
                grade_levels=(),

                selected_academic_year=None,
                selected_subject_id=None,
                selected_grade_level=None,
            )

        selected_academic_year = (
            academic_year_start
            if academic_year_start in academic_years
            else academic_years[0]
        )

        year_rows = tuple(
            item
            for item in rows
            if (
                    item.academic_year_start
                    == selected_academic_year
            )
        )

        subject_ids = tuple(
            sorted(
                {
                    item.subject_id
                    for item in year_rows
                }
            )
        )

        selected_subject_id = (
            subject_id
            if subject_id in subject_ids
            else None
        )

        grade_source_rows = (
            tuple(
                item
                for item in year_rows
                if (
                        item.subject_id
                        == selected_subject_id
                )
            )
            if selected_subject_id is not None
            else year_rows
        )

        grade_levels = tuple(
            sorted(
                {
                    item.grade_level
                    for item in grade_source_rows
                }
            )
        )

        selected_grade_level = (
            grade_level
            if grade_level in grade_levels
            else None
        )

        return KnowledgeQualityDynamicsFilterOptionsDTO(
            academic_years=academic_years,
            subject_ids=subject_ids,
            grade_levels=grade_levels,

            selected_academic_year=(
                selected_academic_year
            ),

            selected_subject_id=(
                selected_subject_id
            ),

            selected_grade_level=(
                selected_grade_level
            ),
        )

    @classmethod
    async def get_region_dynamics(
            cls,
            db: AsyncSession,
            *,
            region_id: int,
            academic_year_start: int,
            subject_id: int | None = None,
            grade_level: int | None = None,
            district_id: int | None = None,
            school_id: int | None = None,
    ) -> KnowledgeQualityDynamicsDTO:
        """
        Общая динамика региона.

        Поддерживаемый drill-down:

            region
                -> subject
                -> grade
                -> district
                -> school

        Регион не получает:
            - class;
            - teacher;
            - student.
        """

        cls._validate_positive_id(
            "region_id",
            region_id,
        )

        cls._validate_academic_year(
            academic_year_start
        )

        cls._validate_optional_positive_id(
            "subject_id",
            subject_id,
        )

        cls._validate_optional_positive_id(
            "grade_level",
            grade_level,
        )

        cls._validate_optional_positive_id(
            "district_id",
            district_id,
        )

        cls._validate_optional_positive_id(
            "school_id",
            school_id,
        )

        rows = (
            await KnowledgeQualityDynamicsRepo
            .get_region_checkpoint_rows(
                db,
                region_id=region_id,
                academic_year_start=(
                    academic_year_start
                ),
                subject_id=subject_id,
                grade_level=grade_level,
                district_id=district_id,
                school_id=school_id,
            )
        )

        points = cls._build_checkpoint_points(
            rows
        )

        return KnowledgeQualityDynamicsDTO(
            scope="region",

            academic_year_start=(
                academic_year_start
            ),

            school_id=school_id,
            district_id=district_id,
            region_id=region_id,

            subject_id=subject_id,
            grade_level=grade_level,

            school_class_id=None,
            teacher_staff_member_id=None,

            points=points,
        )

    # =====================================================
    # REGION -> DISTRICTS
    # =====================================================

    @classmethod
    async def get_region_district_dynamics(
            cls,
            db: AsyncSession,
            *,
            region_id: int,
            academic_year_start: int,
            subject_id: int | None = None,
            grade_level: int | None = None,
    ) -> KnowledgeQualityEntityDynamicsDTO:
        """
        Динамика региона с разбивкой по районам.

        SQL:
            1 запрос — district + checkpoint.

        Затем:
            1 batch-запрос — названия районов.

        N+1 отсутствует.
        """

        cls._validate_positive_id(
            "region_id",
            region_id,
        )

        cls._validate_academic_year(
            academic_year_start
        )

        cls._validate_optional_positive_id(
            "subject_id",
            subject_id,
        )

        cls._validate_optional_positive_id(
            "grade_level",
            grade_level,
        )

        rows = (
            await KnowledgeQualityDynamicsRepo
            .get_region_district_checkpoint_rows(
                db,
                region_id=region_id,
                academic_year_start=(
                    academic_year_start
                ),
                subject_id=subject_id,
                grade_level=grade_level,
            )
        )

        district_ids = cls._extract_entity_ids(
            rows
        )

        district_names = (
            await OrgLookupRepo
            .get_district_names_by_ids(
                db,
                district_ids=district_ids,
            )
            if district_ids
            else {}
        )

        items = cls._build_entity_items(
            rows=rows,
            names=district_names,
        )

        return KnowledgeQualityEntityDynamicsDTO(
            scope="region_districts",

            parent_id=region_id,

            academic_year_start=(
                academic_year_start
            ),

            subject_id=subject_id,
            grade_level=grade_level,

            items=items,
        )

    # =====================================================
    # REGION -> DISTRICT -> SCHOOLS
    # =====================================================

    @classmethod
    async def get_region_school_dynamics(
            cls,
            db: AsyncSession,
            *,
            region_id: int,
            district_id: int,
            academic_year_start: int,
            subject_id: int | None = None,
            grade_level: int | None = None,
    ) -> KnowledgeQualityEntityDynamicsDTO:
        """
        Динамика школ конкретного района
        внутри региональной аналитики.

        Обязательная boundary:
            region_id + district_id

        SQL:
            1 запрос — schools + checkpoints.

        Затем:
            1 batch-запрос — названия школ.
        """

        cls._validate_positive_id(
            "region_id",
            region_id,
        )

        cls._validate_positive_id(
            "district_id",
            district_id,
        )

        cls._validate_academic_year(
            academic_year_start
        )

        cls._validate_optional_positive_id(
            "subject_id",
            subject_id,
        )

        cls._validate_optional_positive_id(
            "grade_level",
            grade_level,
        )

        rows = (
            await KnowledgeQualityDynamicsRepo
            .get_region_school_checkpoint_rows(
                db,
                region_id=region_id,
                district_id=district_id,
                academic_year_start=(
                    academic_year_start
                ),
                subject_id=subject_id,
                grade_level=grade_level,
            )
        )

        school_ids = cls._extract_entity_ids(
            rows
        )

        school_names = (
            await OrgLookupRepo
            .get_school_names_by_ids(
                db,
                school_ids=school_ids,
            )
            if school_ids
            else {}
        )

        items = cls._build_entity_items(
            rows=rows,
            names=school_names,
        )

        return KnowledgeQualityEntityDynamicsDTO(
            scope="region_schools",

            parent_id=district_id,

            academic_year_start=(
                academic_year_start
            ),

            subject_id=subject_id,
            grade_level=grade_level,

            items=items,
        )

    # =====================================================
    # CHECKPOINT POINTS
    # =====================================================

    @classmethod
    def _build_checkpoint_points(
            cls,
            rows: Iterable[
                KnowledgeQualityDynamicsRow
            ],
    ) -> tuple[
        KnowledgeQualityCheckpointDTO,
        ...
    ]:
        """
        Построить одну временную последовательность.

        Порядок не зависит от PostgreSQL enum order.
        Используется CHECKPOINT_POSITION.
        """

        sorted_rows = sorted(
            rows,
            key=lambda item: (
                cls.CHECKPOINT_POSITION.get(
                    item.checkpoint,
                    len(
                        cls.CHECKPOINT_ORDER
                    ),
                )
            ),
        )

        if not sorted_rows:
            return ()

        baseline_quality: Decimal | None = None

        for row in sorted_rows:
            if (
                row.checkpoint
                == AssessmentCheckpoint.BASELINE
            ):
                baseline_quality = (
                    cls._calculate_quality_percent(
                        quality_students=(
                            row.quality_students
                        ),
                        participated_students=(
                            row.participated_students
                        ),
                    )
                )
                break

        points: list[
            KnowledgeQualityCheckpointDTO
        ] = []

        previous_quality: Decimal | None = None

        for row in sorted_rows:

            quality_percent = (
                cls._calculate_quality_percent(
                    quality_students=(
                        row.quality_students
                    ),
                    participated_students=(
                        row.participated_students
                    ),
                )
            )

            delta_previous = (
                cls._calculate_delta(
                    current=quality_percent,
                    reference=previous_quality,
                )
                if previous_quality is not None
                else None
            )

            if (
                row.checkpoint
                == AssessmentCheckpoint.BASELINE
            ):
                delta_baseline = (
                    cls.ZERO
                    if quality_percent is not None
                    else None
                )

            else:
                delta_baseline = (
                    cls._calculate_delta(
                        current=quality_percent,
                        reference=baseline_quality,
                    )
                    if baseline_quality is not None
                    else None
                )

            points.append(
                KnowledgeQualityCheckpointDTO(
                    checkpoint=(
                        row.checkpoint
                    ),

                    checkpoint_label=(
                        row.checkpoint.label_kz
                    ),

                    total_students=(
                        row.total_students
                    ),

                    participated_students=(
                        row.participated_students
                    ),

                    quality_students=(
                        row.quality_students
                    ),

                    quality_percent=(
                        quality_percent
                    ),

                    delta_previous_pp=(
                        delta_previous
                    ),

                    delta_baseline_pp=(
                        delta_baseline
                    ),
                )
            )

            # Последней фактической точкой сравнения
            # считается только точка с рассчитанным
            # quality_percent.
            #
            # Если участвовавших учеников нет,
            # точку нельзя использовать как основу
            # для следующего delta.
            if quality_percent is not None:
                previous_quality = (
                    quality_percent
                )

        return tuple(
            points
        )

    # =====================================================
    # ENTITY ITEMS
    # =====================================================

    @classmethod
    def _build_entity_items(
            cls,
            *,
            rows: Iterable[
                KnowledgeQualityEntityDynamicsRow
            ],
            names: dict[int, str],
    ) -> tuple[
        KnowledgeQualityEntityDynamicsItemDTO,
        ...
    ]:
        """
        Построить drill-down сразу для всех сущностей.

        Здесь нет SQL.

        Все rows уже загружены одним repo-запросом,
        все names уже загружены одним batch-запросом.
        """

        grouped_rows: dict[
            int,
            list[
                KnowledgeQualityDynamicsRow
            ],
        ] = defaultdict(
            list
        )

        for row in rows:
            grouped_rows[
                row.entity_id
            ].append(
                KnowledgeQualityDynamicsRow(
                    checkpoint=(
                        row.checkpoint
                    ),

                    total_students=(
                        row.total_students
                    ),

                    participated_students=(
                        row.participated_students
                    ),

                    grade_5_count=(
                        row.grade_5_count
                    ),

                    grade_4_count=(
                        row.grade_4_count
                    ),

                    quality_students=(
                        row.quality_students
                    ),
                )
            )

        items: list[
            KnowledgeQualityEntityDynamicsItemDTO
        ] = []

        for entity_id in sorted(
            grouped_rows
        ):
            points = (
                cls._build_checkpoint_points(
                    grouped_rows[
                        entity_id
                    ]
                )
            )

            items.append(
                KnowledgeQualityEntityDynamicsItemDTO(
                    entity_id=(
                        entity_id
                    ),

                    entity_name=(
                        names.get(
                            entity_id,
                            f"ID {entity_id}",
                        )
                    ),

                    points=points,
                )
            )

        return tuple(
            items
        )

    # =====================================================
    # MATH
    # =====================================================

    @classmethod
    def _calculate_quality_percent(
            cls,
            *,
            quality_students: int,
            participated_students: int,
    ) -> Decimal | None:
        """
        Качество знаний:

            (5 + 4) / participated * 100

        ABSENT / EXCUSED / NOT_COMPLETED
        в знаменатель не входят.
        """

        if quality_students < 0:
            raise ValueError(
                "quality_students не может быть отрицательным."
            )

        if participated_students < 0:
            raise ValueError(
                "participated_students не может быть отрицательным."
            )

        if quality_students > participated_students:
            raise ValueError(
                "Количество учащихся с качеством знаний "
                "не может превышать количество участников."
            )

        if participated_students == 0:
            return None

        return (
            Decimal(
                quality_students
            )
            * cls.HUNDRED
            / Decimal(
                participated_students
            )
        ).quantize(
            cls.PERCENT_QUANT,
            rounding=ROUND_HALF_UP,
        )

    @classmethod
    def _calculate_delta(
            cls,
            *,
            current: Decimal | None,
            reference: Decimal | None,
    ) -> Decimal | None:
        """
        Изменение в процентных пунктах:

            current - reference
        """

        if (
            current is None
            or reference is None
        ):
            return None

        return (
            current
            - reference
        ).quantize(
            cls.PERCENT_QUANT,
            rounding=ROUND_HALF_UP,
        )

    # =====================================================
    # HELPERS
    # =====================================================

    @staticmethod
    def _extract_entity_ids(
            rows: Iterable[
                KnowledgeQualityEntityDynamicsRow
            ],
    ) -> tuple[int, ...]:
        """
        Собрать уникальные entity_id
        для одного batch lookup.
        """

        return tuple(
            sorted(
                {
                    int(
                        row.entity_id
                    )
                    for row in rows
                }
            )
        )

    # =====================================================
    # VALIDATION
    # =====================================================

    @staticmethod
    def _validate_positive_id(
            name: str,
            value: int,
    ) -> None:
        if value <= 0:
            raise ValueError(
                f"{name} должен быть положительным."
            )

    @classmethod
    def _validate_optional_positive_id(
            cls,
            name: str,
            value: int | None,
    ) -> None:
        if value is None:
            return

        cls._validate_positive_id(
            name,
            value,
        )

    @staticmethod
    def _validate_academic_year(
            academic_year_start: int,
    ) -> None:
        if type(academic_year_start) is not int or academic_year_start <= 0:
            raise ValueError(
                "academic_year_start должен быть положительным целым числом."
            )
