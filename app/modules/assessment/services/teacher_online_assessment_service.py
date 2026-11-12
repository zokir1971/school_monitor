# app/modules/assessment/services/teacher_online_assessment_service.py

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.repositories.teacher_online_assessment_repo import (
    TeacherOnlineAssessmentRepo,
)
from app.modules.assessment.schemas.teacher_online_assessment_schemas import (
    TeacherOnlineAssessmentItemDTO,
    TeacherOnlineAssessmentsPageDTO, TeacherOnlineAssessmentGroupsPageDTO, TeacherOnlineAssessmentGroupItemDTO,
    TeacherOnlineAssessmentStudentsPageDTO, TeacherOnlineAssessmentStudentItemDTO,
)


class TeacherOnlineAssessmentService:
    """
    Read service рабочего кабинета
    ONLINE Assessment учителя.

    Repository:
        SQL / teacher security boundary / aggregates.

    Service:
        преобразование read-model в DTO страницы.

    Web:
        только dependency -> service -> render.
    """

    # =====================================================
    # LIST PAGE
    # =====================================================

    @classmethod
    async def get_list_page(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
        teacher_staff_member_id: int,
    ) -> TeacherOnlineAssessmentsPageDTO:
        """
        Получить главную страницу ONLINE Assessment
        текущего учителя.
        """

        if school_id <= 0:
            raise ValueError(
                "school_id дұрыс емес."
            )

        if teacher_staff_member_id <= 0:
            raise ValueError(
                "teacher_staff_member_id дұрыс емес."
            )

        rows = (
            await TeacherOnlineAssessmentRepo
            .get_many_for_teacher(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
            )
        )

        items = tuple(
            TeacherOnlineAssessmentItemDTO(
                assessment_id=row.assessment_id,

                title=row.title,
                subject_name=row.subject_name,

                status=row.status,

                scheduled_at=row.scheduled_at,
                started_at=row.started_at,
                completed_at=row.completed_at,

                group_count=row.group_count,
                total_students=row.total_students,

                assigned_count=row.assigned_count,
                in_progress_count=(
                    row.in_progress_count
                ),
                submitted_count=(
                    row.submitted_count
                ),
                completed_count=(
                    row.completed_count
                ),

                absent_count=row.absent_count,
                excused_count=row.excused_count,
                not_completed_count=(
                    row.not_completed_count
                ),
            )
            for row in rows
        )

        return TeacherOnlineAssessmentsPageDTO(
            items=items,
        )

    # =====================================================
    # GROUPS PAGE
    # =====================================================

    @classmethod
    async def get_groups_page(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
        teacher_staff_member_id: int,
        assessment_id: int,
    ) -> TeacherOnlineAssessmentGroupsPageDTO:
        """
        Получить группы конкретного ONLINE Assessment,
        принадлежащие текущему учителю.
        """

        if school_id <= 0:
            raise ValueError(
                "school_id дұрыс емес."
            )

        if teacher_staff_member_id <= 0:
            raise ValueError(
                "teacher_staff_member_id дұрыс емес."
            )

        if assessment_id <= 0:
            raise ValueError(
                "assessment_id дұрыс емес."
            )

        rows = (
            await TeacherOnlineAssessmentRepo
            .get_groups_for_teacher(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
                assessment_id=assessment_id,
            )
        )

        items = tuple(
            TeacherOnlineAssessmentGroupItemDTO(
                assessment_group_id=(
                    row.assessment_group_id
                ),
                assessment_id=row.assessment_id,

                school_class_id=(
                    row.school_class_id
                ),
                class_name=row.class_name,

                grade_level=row.grade_level,
                academic_year_start=(
                    row.academic_year_start
                ),

                total_students=(
                    row.total_students
                ),

                assigned_count=(
                    row.assigned_count
                ),
                in_progress_count=(
                    row.in_progress_count
                ),
                submitted_count=(
                    row.submitted_count
                ),
                completed_count=(
                    row.completed_count
                ),

                absent_count=(
                    row.absent_count
                ),
                excused_count=(
                    row.excused_count
                ),
                not_completed_count=(
                    row.not_completed_count
                ),
            )
            for row in rows
        )

        return TeacherOnlineAssessmentGroupsPageDTO(
            assessment_id=assessment_id,
            items=items,
        )

    # =====================================================
    # STUDENTS PAGE
    # =====================================================

    @classmethod
    async def get_students_page(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            assessment_group_id: int,
    ) -> TeacherOnlineAssessmentStudentsPageDTO:
        """
        Получить страницу участников одной группы
        ONLINE Assessment.
        """

        if school_id <= 0:
            raise ValueError(
                "school_id дұрыс емес."
            )

        if teacher_staff_member_id <= 0:
            raise ValueError(
                "teacher_staff_member_id дұрыс емес."
            )

        if assessment_group_id <= 0:
            raise ValueError(
                "assessment_group_id дұрыс емес."
            )

        # =================================================
        # HEADER
        # =================================================

        header = (
            await TeacherOnlineAssessmentRepo
            .get_group_header_for_teacher(
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

        if header is None:
            return TeacherOnlineAssessmentStudentsPageDTO(
                assessment_id=0,
                assessment_group_id=assessment_group_id,
                items=(),
            )

        # =================================================
        # STUDENTS
        # =================================================

        rows = (
            await TeacherOnlineAssessmentRepo
            .get_students_for_teacher(
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

        items = tuple(
            TeacherOnlineAssessmentStudentItemDTO(
                assessment_student_id=(
                    row.assessment_student_id
                ),
                assessment_group_id=(
                    row.assessment_group_id
                ),
                assessment_id=(
                    row.assessment_id
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

                assigned_at=(
                    row.assigned_at
                ),
                started_at=(
                    row.started_at
                ),
                completed_at=(
                    row.completed_at
                ),

                result_score=(
                    row.result_score
                ),
                result_max_score=(
                    row.result_max_score
                ),
                result_percent=(
                    row.result_percent
                ),
                result_grade=(
                    row.result_grade
                ),
            )
            for row in rows
        )

        return TeacherOnlineAssessmentStudentsPageDTO(
            assessment_id=(
                header.assessment_id
            ),
            assessment_group_id=(
                header.assessment_group_id
            ),
            items=items,
        )
