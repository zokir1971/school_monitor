# app/modules/assessment/services/assessment_list_service.py

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.enums import (
    AssessmentStatus,
)
from app.modules.assessment.repositories.assessment_repo import (
    AssessmentRepo,
)
from app.modules.assessment.schemas.assessment_list_schemas import (
    AssessmentListFilterOptionsDTO,
    AssessmentListItemDTO,
    AssessmentListPageDTO,
    AssessmentListSubjectOptionDTO,
)


class AssessmentListService:
    """
    Формирование операционного списка Assessment.

    Используется:
        - SCHOOL_ADMIN / SCHOOL_STAFF;
        - TEACHER.

    Сервис не выполняет ORM-запросы внутри циклов.

    Количество SQL-запросов на страницу фиксировано:
        1. строки Assessment;
        2. учебные годы;
        3. предметы;
        4. параллели.

    Количество запросов не зависит от:
        - количества Assessment;
        - количества групп;
        - количества учеников.
    """

    # =========================================================
    # SCHOOL LIST
    # =========================================================
    @classmethod
    async def get_school_page(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            status: AssessmentStatus | None = None,
    ) -> AssessmentListPageDTO:
        """
        Операционный список Assessment школы.
        Scope:
            school_id
        Используется:
            SCHOOL_ADMIN;
            SCHOOL_STAFF.
        """

        cls._validate_school_id(
            school_id
        )

        # =========================================================
        # LIST ROWS
        # =========================================================

        rows = (
            await AssessmentRepo.get_school_list_rows(
                db,
                school_id=school_id,
                academic_year_start=(
                    academic_year_start
                ),
                subject_id=(
                    subject_id
                ),
                grade_level=(
                    grade_level
                ),
                status=(
                    status
                ),
            )
        )

        # =========================================================
        # FILTER OPTIONS
        # =========================================================

        filter_options = (
            await cls.get_school_filter_options(
                db,
                school_id=school_id,
            )
        )

        # =========================================================
        # PAGE DTO
        # =========================================================

        return cls._build_page(
            school_id=school_id,
            rows=rows,
            filter_options=filter_options,
            academic_year_start=(
                academic_year_start
            ),
            subject_id=(
                subject_id
            ),
            grade_level=(
                grade_level
            ),
            status=(
                status
            ),
            teacher_scope=False,
        )

    # =========================================================
    # TEACHER LIST
    # =========================================================
    @classmethod
    async def get_teacher_page(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            status: AssessmentStatus | None = None,
    ) -> AssessmentListPageDTO:
        """
        Операционный список Assessment текущего учителя.

        Security scope:
            school_id
            +
            AssessmentGroup.teacher_staff_member_id

        Учитель видит только те Assessment,
        где у него есть собственная AssessmentGroup.

        Данные строки:
            class_names;
            teacher_names;
            participant statistics

        также ограничены группами текущего учителя.
        """

        cls._validate_school_id(
            school_id
        )

        cls._validate_teacher_staff_member_id(
            teacher_staff_member_id
        )

        rows = (
            await AssessmentRepo.get_teacher_list_rows(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
                academic_year_start=academic_year_start,
                subject_id=subject_id,
                grade_level=grade_level,
                status=status,
            )
        )

        filter_options = (
            await cls.get_teacher_filter_options(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
            )
        )

        return cls._build_page(
            school_id=school_id,
            rows=rows,
            filter_options=filter_options,
            academic_year_start=academic_year_start,
            subject_id=subject_id,
            grade_level=grade_level,
            status=status,
            teacher_scope=True,
        )

    # =========================================================
    # SCHOOL FILTER OPTIONS
    # =========================================================

    @classmethod
    async def get_school_filter_options(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
    ) -> AssessmentListFilterOptionsDTO:
        cls._validate_school_id(
            school_id
        )

        academic_years = (
            await AssessmentRepo
            .get_school_list_academic_years(
                db,
                school_id=school_id,
            )
        )

        subject_rows = (
            await AssessmentRepo
            .get_school_list_subject_rows(
                db,
                school_id=school_id,
            )
        )

        grade_levels = (
            await AssessmentRepo
            .get_school_list_grade_levels(
                db,
                school_id=school_id,
            )
        )

        return cls._build_filter_options(
            academic_years=academic_years,
            subject_rows=subject_rows,
            grade_levels=grade_levels,
        )

    # =========================================================
    # TEACHER FILTER OPTIONS
    # =========================================================

    @classmethod
    async def get_teacher_filter_options(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
    ) -> AssessmentListFilterOptionsDTO:
        cls._validate_school_id(
            school_id
        )

        cls._validate_teacher_staff_member_id(
            teacher_staff_member_id
        )

        academic_years = (
            await AssessmentRepo
            .get_teacher_list_academic_years(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
            )
        )

        subject_rows = (
            await AssessmentRepo
            .get_teacher_list_subject_rows(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
            )
        )

        grade_levels = (
            await AssessmentRepo
            .get_teacher_list_grade_levels(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
            )
        )

        return cls._build_filter_options(
            academic_years=academic_years,
            subject_rows=subject_rows,
            grade_levels=grade_levels,
        )

    # =========================================================
    # PAGE BUILDER
    # =========================================================

    @classmethod
    def _build_page(
            cls,
            *,
            school_id: int,
            rows,
            filter_options: AssessmentListFilterOptionsDTO,
            academic_year_start: int | None,
            subject_id: int | None,
            grade_level: int | None,
            status: AssessmentStatus | None,
            teacher_scope: bool,
    ) -> AssessmentListPageDTO:
        """
        Собрать DTO страницы из уже полученных SQL rows.

        Здесь нет обращений к БД.
        """

        items: list[
            AssessmentListItemDTO
        ] = []

        draft_count = 0
        completed_count = 0

        for row in rows:
            item = cls._build_item(
                row=row,
                teacher_scope=teacher_scope,
            )

            items.append(
                item
            )

            if (
                    item.status
                    == AssessmentStatus.DRAFT.value
            ):
                draft_count += 1

            if (
                    item.status
                    == AssessmentStatus.COMPLETED.value
            ):
                completed_count += 1

        return AssessmentListPageDTO(
            school_id=school_id,

            items=tuple(
                items
            ),

            filter_options=filter_options,

            total_count=len(
                items
            ),

            draft_count=draft_count,
            completed_count=completed_count,

            selected_academic_year=(
                academic_year_start
            ),

            selected_subject_id=(
                subject_id
            ),

            selected_grade_level=(
                grade_level
            ),

            selected_status=(
                status.value
                if status is not None
                else None
            ),
        )

    # =========================================================
    # ITEM BUILDER
    # =========================================================

    @classmethod
    def _build_item(
            cls,
            *,
            row,
            teacher_scope: bool,
    ) -> AssessmentListItemDTO:
        """
        Собрать одну строку списка.

        Никаких SQL-запросов здесь нет.
        """

        assessment_type = (
            row.assessment_type
        )

        assessment_status = (
            row.status
        )

        input_mode = (
            row.input_mode
        )

        total_students = int(
            row.total_students
            or 0
        )

        completed_students = int(
            row.completed_students
            or 0
        )

        absent_students = int(
            row.absent_students
            or 0
        )

        processed_students = int(
            row.processed_students
            or 0
        )

        result_count = int(
            row.result_count
            or 0
        )

        class_names = cls._normalize_names(
            getattr(
                row,
                "class_names",
                None,
            )
        )

        teacher_names = cls._normalize_names(
            getattr(
                row,
                "teacher_names",
                None,
            )
        )

        can_complete = (
            cls._can_complete(
                assessment_status=(
                    assessment_status
                ),
                max_score=row.max_score,
                total_students=total_students,
                completed_students=(
                    completed_students
                ),
                processed_students=(
                    processed_students
                ),
                result_count=result_count,
                teacher_scope=teacher_scope,
                all_groups_belong_to_teacher=(
                    bool(
                        getattr(
                            row,
                            "all_groups_belong_to_teacher",
                            False,
                        )
                    )
                ),
            )
        )

        return AssessmentListItemDTO(
            assessment_id=(
                row.assessment_id
            ),

            title=(
                row.title
                or "—"
            ),

            subject_id=(
                row.subject_id
            ),

            subject_name=(
                row.subject_name
                or "—"
            ),

            assessment_type=(
                assessment_type.value
            ),

            assessment_type_label=(
                assessment_type.label_kz
            ),

            status=(
                assessment_status.value
            ),

            status_label=(
                assessment_status.label_kz
            ),

            input_mode=(
                input_mode.value
            ),

            input_mode_label=(
                input_mode.label_kz
            ),

            max_score=(
                row.max_score
            ),

            class_names=(
                class_names
            ),

            teacher_names=(
                teacher_names
            ),

            total_students=(
                total_students
            ),

            completed_students=(
                completed_students
            ),

            absent_students=(
                absent_students
            ),

            result_count=(
                result_count
            ),

            processed_students=(
                processed_students
            ),

            can_complete=(
                can_complete
            ),
        )

    # =========================================================
    # FILTER OPTIONS BUILDER
    # =========================================================

    @staticmethod
    def _build_filter_options(
            *,
            academic_years: tuple[int, ...],
            subject_rows,
            grade_levels: tuple[int, ...],
    ) -> AssessmentListFilterOptionsDTO:
        """
        Преобразовать SQL rows фильтров в DTO.

        SQL-запросы здесь не выполняются.
        """

        subjects = tuple(
            AssessmentListSubjectOptionDTO(
                subject_id=(
                    row.subject_id
                ),
                subject_name=(
                    row.subject_name
                    or "—"
                ),
            )
            for row in subject_rows
        )

        return AssessmentListFilterOptionsDTO(
            academic_years=tuple(
                academic_years
            ),

            subjects=subjects,

            grade_levels=tuple(
                grade_levels
            ),
        )

    # =========================================================
    # COMPLETE AVAILABILITY
    # =========================================================

    @staticmethod
    def _can_complete(
            *,
            assessment_status: AssessmentStatus,
            max_score,
            total_students: int,
            completed_students: int,
            processed_students: int,
            result_count: int,
            teacher_scope: bool,
            all_groups_belong_to_teacher: bool,
    ) -> bool:
        """
        Определить, имеет ли смысл показывать кнопку
        завершения Assessment.

        Это UI-предикат, а не security boundary.

        AssessmentCompletionService повторно выполняет
        полную авторитетную проверку перед COMMIT.
        """

        if assessment_status in {
            AssessmentStatus.COMPLETED,
            AssessmentStatus.ARCHIVED,
        }:
            return False

        if (
                max_score is None
                or max_score <= 0
        ):
            return False

        if total_students <= 0:
            return False

        if (
                processed_students
                != total_students
        ):
            return False

        # Каждый COMPLETED должен иметь результат.
        #
        # result_count может быть больше completed_students,
        # если в БД присутствуют результаты и для других
        # финальных статусов, поэтому проверяем >=.
        if (
                result_count
                < completed_students
        ):
            return False

        if (
                teacher_scope
                and not all_groups_belong_to_teacher
        ):
            return False

        return True

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _normalize_names(
            values,
    ) -> tuple[str, ...]:
        """
        Нормализовать PostgreSQL array_agg результат.

        Удаляет:
            - NULL;
            - пустые строки;
            - дубли.

        Сохраняет стабильный порядок для UI.
        """

        if not values:
            return ()

        normalized = {
            str(value).strip()
            for value in values
            if (
                value is not None
                and str(value).strip()
            )
        }

        return tuple(
            sorted(
                normalized
            )
        )

    @staticmethod
    def _validate_school_id(
            school_id: int,
    ) -> None:
        if school_id <= 0:
            raise ValueError(
                "Некорректный school_id."
            )

    @staticmethod
    def _validate_teacher_staff_member_id(
            teacher_staff_member_id: int,
    ) -> None:
        if teacher_staff_member_id <= 0:
            raise ValueError(
                "Некорректный teacher_staff_member_id."
            )
