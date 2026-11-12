# app/modules/assessment/services/teacher_assessment_result_service.py

from __future__ import annotations

from app.modules.assessment.helpers.teacher_answer_presentation import question_view, response_lines

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.repositories.teacher_assessment_result_repo import (
    TeacherAssessmentResultRepo,
)
from app.modules.assessment.schemas.teacher_result_schemas import (
    TeacherAssessmentStudentsPageDTO,
    TeacherClassAssessmentItemDTO,
    TeacherClassAssessmentsPageDTO,
    TeacherStudentResultDTO, TeacherStudentReviewPageDTO, TeacherStudentAnswerReviewDTO,
)


class TeacherAssessmentResultService:
    """
    Teacher drill-down service.

    Уровни:
        class -> assessments
        assessment group -> students
    """

    # =====================================================
    # CLASS -> ASSESSMENTS
    # =====================================================

    @classmethod
    async def get_class_assessments(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
        teacher_staff_member_id: int,
        school_class_id: int,
        academic_year_start: int | None = None,
        subject_id: int | None = None,
    ) -> TeacherClassAssessmentsPageDTO:
        rows = (
            await TeacherAssessmentResultRepo
            .get_teacher_class_assessments(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
                school_class_id=(
                    school_class_id
                ),
                academic_year_start=(
                    academic_year_start
                ),
                subject_id=subject_id,
            )
        )

        if not rows:
            raise ValueError(
                "Осы сынып бойынша Assessment табылмады."
            )

        first = rows[0]

        items = tuple(
            TeacherClassAssessmentItemDTO(
                assessment_id=(
                    row.assessment_id
                ),
                assessment_group_id=(
                    row.assessment_group_id
                ),

                title=row.title,
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

                max_score=(
                    row.max_score
                ),

                total_students=(
                    row.total_students
                ),
                participated_students=(
                    row.participated_students
                ),
            )
            for row in rows
        )

        return TeacherClassAssessmentsPageDTO(
            school_class_id=(
                first.school_class_id
            ),
            class_name=(
                first.class_name
            ),

            academic_year_start=(
                academic_year_start
            ),
            subject_id=subject_id,

            items=items,
        )

    # =====================================================
    # ASSESSMENT GROUP -> STUDENTS
    # =====================================================

    @classmethod
    async def get_assessment_students(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
        teacher_staff_member_id: int,
        assessment_group_id: int,
    ) -> TeacherAssessmentStudentsPageDTO:
        rows = (
            await TeacherAssessmentResultRepo
            .get_teacher_group_student_rows(
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
                "Assessment нәтижелері табылмады."
            )

        first = rows[0]

        students = tuple(
            TeacherStudentResultDTO(
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
                    row.participation_status
                ),

                score=row.score,
                max_score=row.max_score,
                percent=row.percent,
                grade=row.grade,
            )
            for row in rows
        )

        return TeacherAssessmentStudentsPageDTO(
            assessment_id=(
                first.assessment_id
            ),
            assessment_group_id=(
                first.assessment_group_id
            ),

            title=(
                first.assessment_title
            ),
            subject_name=(
                first.subject_name
            ),
            input_mode=(
                first.assessment_input_mode
            ),

            school_class_id=(
                first.school_class_id
            ),
            class_name=(
                first.class_name
            ),
            grade_level=(
                first.grade_level
            ),

            max_score=(
                first.assessment_max_score
            ),

            students=students,
        )
    
    # =====================================================
    # STUDENT -> ANSWERS
    # =====================================================

    @classmethod
    async def get_student_review_page(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            assessment_student_id: int,
    ) -> TeacherStudentReviewPageDTO:
        """
        Получить страницу просмотра ответов
        конкретного ученика ONLINE Assessment.
        """

        if school_id <= 0:
            raise ValueError(
                "school_id дұрыс емес."
            )

        if teacher_staff_member_id <= 0:
            raise ValueError(
                "teacher_staff_member_id дұрыс емес."
            )

        if assessment_student_id <= 0:
            raise ValueError(
                "assessment_student_id дұрыс емес."
            )

        # =================================================
        # HEADER / RESULT
        # =================================================

        header = (
            await TeacherAssessmentResultRepo
            .get_teacher_student_review_header(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
                assessment_student_id=(
                    assessment_student_id
                ),
            )
        )

        if header is None:
            raise ValueError(
                "Оқушының жұмысы табылмады "
                "немесе оны көруге рұқсат жоқ."
            )

        # =================================================
        # ANSWERS
        # =================================================

        rows = (
            await TeacherAssessmentResultRepo
            .get_teacher_student_answers(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
                assessment_student_id=(
                    assessment_student_id
                ),
            )
        )

        answers = tuple(
            TeacherStudentAnswerReviewDTO(
                answer_id=row.answer_id,
                question_id=row.question_id,

                question_type=row.question_type,
                question_text=row.question_text,
                question_order_no=(
                    row.question_order_no
                ),

                answer_data=row.answer_data,
                question_view=(view := question_view(row)),
                response_lines=response_lines(view,row.answer_data),

                status=row.status,

                score=row.score,
                max_score=row.max_score,

                is_correct=row.is_correct,

                checked_by_user_id=(
                    row.checked_by_user_id
                ),
            )
            for row in rows
        )

        # =================================================
        # PAGE DTO
        # =================================================

        return TeacherStudentReviewPageDTO(
            assessment_id=(
                header.assessment_id
            ),

            assessment_group_id=(
                header.assessment_group_id
            ),

            assessment_student_id=(
                header.assessment_student_id
            ),

            student_id=(
                header.student_id
            ),

            student_name=(
                header.student_name
            ),

            participation_status=(
                header.participation_status
            ),

            result_score=(
                header.score
            ),

            result_max_score=(
                header.max_score
            ),

            result_percent=(
                header.percent
            ),

            result_grade=(
                header.grade
            ),

            answers=answers,
        )
