# app/modules/assessment/services/learning_objective_analysis_service.py

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.repositories.teacher_assessment_result_repo import (
    TeacherAssessmentResultRepo,
)
from app.modules.assessment.schemas.teacher_result_schemas import (
    TeacherAssessmentObjectivesPageDTO,
    TeacherObjectiveStudentResultDTO,
    TeacherObjectiveStudentsPageDTO,
    TeacherObjectiveSummaryDTO,
)


class LearningObjectiveAnalysisService:
    """
    Аналитика результатов по учебным целям.

    Service Layer:

        - не выполняет SQL;
        - не пересчитывает агрегаты, уже рассчитанные repo;
        - проверяет наличие и доступность данных;
        - преобразует repository rows в DTO страницы.

    Repository Layer является единственным местом,
    где выполняются агрегирующие SQL-запросы.

    Источник данных:

        AssessmentObjective
            ↓
        AssessmentObjectiveResult
            ↓
        AssessmentResult
            ↓
        AssessmentStudent
            ↓
        AssessmentGroup
    """

    # =====================================================
    # TEACHER — ASSESSMENT OBJECTIVES
    # =====================================================

    @classmethod
    async def get_teacher_assessment_objectives_page(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
        teacher_staff_member_id: int,
        assessment_group_id: int,
    ) -> TeacherAssessmentObjectivesPageDTO:
        """
        Получить аналитику всех учебных целей
        конкретного AssessmentGroup учителя.

        Одна строка:
            одна AssessmentObjective.

        Security boundary полностью обеспечивается
        repository query через:

            school_id
            teacher_staff_member_id
            assessment_group_id
        """

        cls._validate_teacher_scope(
            school_id=school_id,
            teacher_staff_member_id=(
                teacher_staff_member_id
            ),
        )

        if assessment_group_id <= 0:
            raise ValueError(
                "Некорректный assessment_group_id."
            )

        rows = (
            await TeacherAssessmentResultRepo
            .get_teacher_group_objective_summary(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
                assessment_group_id=(
                    assessment_group_id
                ),
            )
        )

        if not rows:
            raise ValueError(
                "Assessment тобы табылмады, "
                "мұғалімге тиесілі емес немесе "
                "бұл Assessment оқу мақсаттарын "
                "қолданбайды."
            )

        first_row = rows[0]

        objectives = tuple(
            TeacherObjectiveSummaryDTO(
                assessment_id=(
                    row.assessment_id
                ),

                assessment_group_id=(
                    row.assessment_group_id
                ),

                assessment_title=(
                    row.assessment_title
                ),

                subject_name=(
                    row.subject_name
                ),

                school_class_id=(
                    row.school_class_id
                ),

                class_name=(
                    row.class_name
                ),

                grade_level=(
                    row.grade_level
                ),

                assessment_objective_id=(
                    row.assessment_objective_id
                ),

                learning_objective_id=(
                    row.learning_objective_id
                ),

                objective_code=(
                    row.objective_code
                ),

                objective_title=(
                    row.objective_title
                ),

                order_no=(
                    row.order_no
                ),

                objective_max_score=(
                    row.objective_max_score
                ),

                participated_students=(
                    row.participated_students
                ),

                score_sum=(
                    row.score_sum
                ),

                max_score_sum=(
                    row.max_score_sum
                ),

                mastery_percent=(
                    row.mastery_percent
                ),
            )
            for row in rows
        )

        return (
            TeacherAssessmentObjectivesPageDTO(
                assessment_id=(
                    first_row.assessment_id
                ),

                assessment_group_id=(
                    first_row.assessment_group_id
                ),

                assessment_title=(
                    first_row.assessment_title
                ),

                subject_name=(
                    first_row.subject_name
                ),

                school_class_id=(
                    first_row.school_class_id
                ),

                class_name=(
                    first_row.class_name
                ),

                grade_level=(
                    first_row.grade_level
                ),

                objectives=objectives,
            )
        )

    # =====================================================
    # TEACHER — OBJECTIVE STUDENTS
    # =====================================================

    @classmethod
    async def get_teacher_objective_students_page(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
        teacher_staff_member_id: int,
        assessment_group_id: int,
        assessment_objective_id: int,
    ) -> TeacherObjectiveStudentsPageDTO:
        """
        Получить drill-down одной учебной цели:

            учебная цель
                ↓
            ученики класса
                ↓
            индивидуальные результаты

        Возвращаются и ученики без результата:

            ABSENT
            EXCUSED
            NOT_COMPLETED

        Поэтому Service Layer не фильтрует строки.
        """

        cls._validate_teacher_scope(
            school_id=school_id,
            teacher_staff_member_id=(
                teacher_staff_member_id
            ),
        )

        if assessment_group_id <= 0:
            raise ValueError(
                "Некорректный assessment_group_id."
            )

        if assessment_objective_id <= 0:
            raise ValueError(
                "Некорректный assessment_objective_id."
            )

        rows = (
            await TeacherAssessmentResultRepo
            .get_teacher_objective_student_rows(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
                assessment_group_id=(
                    assessment_group_id
                ),
                assessment_objective_id=(
                    assessment_objective_id
                ),
            )
        )

        if not rows:
            raise ValueError(
                "Оқу мақсаты табылмады "
                "немесе мұғалімнің осы Assessment "
                "тобына қатысы жоқ."
            )

        first_row = rows[0]

        students = tuple(
            TeacherObjectiveStudentResultDTO(
                assessment_student_id=(
                    row.assessment_student_id
                ),

                student_id=(
                    row.student_id
                ),

                student_name=(
                    row.student_name
                ),

                participation_status=(
                    row.participation_status.value
                ),

                participation_status_label=(
                    row.participation_status.label_kz
                ),

                score=(
                    row.score
                ),

                max_score=(
                    row.max_score
                ),

                percent=(
                    row.percent
                ),
            )
            for row in rows
        )

        return (
            TeacherObjectiveStudentsPageDTO(
                assessment_id=(
                    first_row.assessment_id
                ),

                assessment_group_id=(
                    first_row.assessment_group_id
                ),

                assessment_title=(
                    first_row.assessment_title
                ),

                subject_name=(
                    first_row.subject_name
                ),

                school_class_id=(
                    first_row.school_class_id
                ),

                class_name=(
                    first_row.class_name
                ),

                grade_level=(
                    first_row.grade_level
                ),

                assessment_objective_id=(
                    first_row.assessment_objective_id
                ),

                learning_objective_id=(
                    first_row.learning_objective_id
                ),

                objective_code=(
                    first_row.objective_code
                ),

                objective_title=(
                    first_row.objective_title
                ),

                objective_max_score=(
                    first_row.objective_max_score
                ),

                students=students,
            )
        )

    # =====================================================
    # VALIDATION
    # =====================================================

    @staticmethod
    def _validate_teacher_scope(
        *,
        school_id: int,
        teacher_staff_member_id: int,
    ) -> None:
        """
        Базовая защита входных scope-параметров.

        Реальная проверка принадлежности данных
        выполняется repository query.
        """

        if school_id <= 0:
            raise ValueError(
                "Некорректный school_id."
            )

        if teacher_staff_member_id <= 0:
            raise ValueError(
                "Некорректный teacher_staff_member_id."
            )
