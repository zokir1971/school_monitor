# app/modules/assessment/repositories/teacher_online_assessment_repo.py

from __future__ import annotations
from app.modules.assessment.repositories.assessment_name_columns import title_column

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import (
    case,
    distinct,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from app.modules.assessment.enums import (
    AssessmentInputMode,
    AssessmentParticipationStatus,
    AssessmentStatus, AssessmentGrade,
)
from app.modules.assessment.models import (
    Assessment,
    AssessmentGroup,
    AssessmentStudent, AssessmentResult,
)


# =========================================================
# READ MODELS
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherOnlineAssessmentRow:
    """
    Агрегированная строка ONLINE Assessment
    для рабочего кабинета учителя.

    Одна строка = один Assessment.
    """

    assessment_id: int

    title: str
    subject_name: str

    status: AssessmentStatus

    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None

    group_count: int
    total_students: int

    assigned_count: int
    in_progress_count: int
    submitted_count: int
    completed_count: int

    absent_count: int
    excused_count: int
    not_completed_count: int


@dataclass(frozen=True, slots=True)
class TeacherOnlineAssessmentGroupRow:
    """
    Агрегированная строка группы ONLINE Assessment
    для рабочего кабинета учителя.

    Одна строка = одна AssessmentGroup,
    принадлежащая текущему учителю.
    """

    assessment_group_id: int
    assessment_id: int

    school_class_id: int
    class_name: str

    grade_level: int | None
    academic_year_start: int | None

    total_students: int

    assigned_count: int
    in_progress_count: int
    submitted_count: int
    completed_count: int

    absent_count: int
    excused_count: int
    not_completed_count: int


@dataclass(frozen=True, slots=True)
class TeacherOnlineAssessmentStudentRow:
    """
    Строка участника группы ONLINE Assessment
    в рабочем кабинете учителя.

    Одна строка = один AssessmentStudent.
    """

    assessment_student_id: int
    assessment_group_id: int
    assessment_id: int

    student_id: int
    student_name: str

    participation_status: AssessmentParticipationStatus

    assigned_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None

    result_score: Decimal | None
    result_max_score: Decimal | None
    result_percent: Decimal | None
    result_grade: AssessmentGrade | None


@dataclass(frozen=True, slots=True)
class TeacherOnlineAssessmentGroupHeaderRow:
    """
    Метаданные группы ONLINE Assessment.

    Используется как header страницы студентов
    и одновременно подтверждает доступ учителя
    к конкретной группе.
    """

    assessment_group_id: int
    assessment_id: int

    school_class_id: int
    class_name: str

    grade_level: int | None
    academic_year_start: int | None


# =========================================================
# REPOSITORY
# =========================================================


class TeacherOnlineAssessmentRepo:
    """
    Read-only repository рабочего кабинета
    ONLINE Assessment учителя.

    Security boundary:

        school_id
        +
        teacher_staff_member_id

    Учитель получает только те Assessment,
    где у него существует собственная AssessmentGroup.
    """

    # =====================================================
    # LIST
    # =====================================================

    @staticmethod
    async def get_many_for_teacher(
        db: AsyncSession,
        *,
        school_id: int,
        teacher_staff_member_id: int,
    ) -> list[TeacherOnlineAssessmentRow]:
        """
        Получить ONLINE Assessment учителя
        с агрегатами по его классам и ученикам.

        Важно:

        - только AssessmentInputMode.ONLINE;
        - только текущая школа;
        - учитываются только AssessmentGroup,
          принадлежащие текущему учителю;
        - один Assessment возвращается одной строкой;
        - без lazy loading;
        - без N+1.
        """

        stmt = (
            select(
                # -----------------------------------------
                # ASSESSMENT
                # -----------------------------------------

                Assessment.id.label(
                    "assessment_id"
                ),

                title_column().label(
                    "title"
                ),

                func.coalesce(
                    Assessment.subject_name_snapshot,
                    "",
                ).label(
                    "subject_name"
                ),

                Assessment.status.label(
                    "status"
                ),

                Assessment.scheduled_at.label(
                    "scheduled_at"
                ),

                Assessment.started_at.label(
                    "started_at"
                ),

                Assessment.completed_at.label(
                    "completed_at"
                ),

                # -----------------------------------------
                # GROUPS
                # -----------------------------------------

                func.count(
                    distinct(
                        AssessmentGroup.id
                    )
                ).label(
                    "group_count"
                ),

                # -----------------------------------------
                # STUDENTS
                # -----------------------------------------

                func.count(
                    AssessmentStudent.id
                ).label(
                    "total_students"
                ),

                func.count(
                    case(
                        (
                            AssessmentStudent.participation_status
                            == AssessmentParticipationStatus.ASSIGNED,
                            1,
                        )
                    )
                ).label(
                    "assigned_count"
                ),

                func.count(
                    case(
                        (
                            AssessmentStudent.participation_status
                            == AssessmentParticipationStatus.IN_PROGRESS,
                            1,
                        )
                    )
                ).label(
                    "in_progress_count"
                ),

                func.count(
                    case(
                        (
                            AssessmentStudent.participation_status
                            == AssessmentParticipationStatus.SUBMITTED,
                            1,
                        )
                    )
                ).label(
                    "submitted_count"
                ),

                func.count(
                    case(
                        (
                            AssessmentStudent.participation_status
                            == AssessmentParticipationStatus.COMPLETED,
                            1,
                        )
                    )
                ).label(
                    "completed_count"
                ),

                func.count(
                    case(
                        (
                            AssessmentStudent.participation_status
                            == AssessmentParticipationStatus.ABSENT,
                            1,
                        )
                    )
                ).label(
                    "absent_count"
                ),

                func.count(
                    case(
                        (
                            AssessmentStudent.participation_status
                            == AssessmentParticipationStatus.EXCUSED,
                            1,
                        )
                    )
                ).label(
                    "excused_count"
                ),

                func.count(
                    case(
                        (
                            AssessmentStudent.participation_status
                            == AssessmentParticipationStatus.NOT_COMPLETED,
                            1,
                        )
                    )
                ).label(
                    "not_completed_count"
                ),
            )

            # =============================================
            # ASSESSMENT -> TEACHER GROUPS
            # =============================================

            .join(
                AssessmentGroup,
                (
                    AssessmentGroup.assessment_id
                    == Assessment.id
                )
                & (
                    AssessmentGroup.school_id
                    == Assessment.school_id
                ),
            )

            # =============================================
            # GROUP -> STUDENTS
            # =============================================

            .outerjoin(
                AssessmentStudent,
                (
                    AssessmentStudent.assessment_group_id
                    == AssessmentGroup.id
                )
                & (
                    AssessmentStudent.school_id
                    == AssessmentGroup.school_id
                ),
            )

            # =============================================
            # SECURITY / ONLINE
            # =============================================

            .where(
                Assessment.school_id
                == school_id,

                Assessment.input_mode
                == AssessmentInputMode.ONLINE,

                AssessmentGroup.school_id
                == school_id,

                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,
            )

            # =============================================
            # GROUP BY
            # =============================================

            .group_by(
                Assessment.id,
                title_column().label("title"),
                Assessment.subject_name_snapshot,
                Assessment.status,
                Assessment.scheduled_at,
                Assessment.started_at,
                Assessment.completed_at,
            )

            # =============================================
            # ORDER
            # =============================================

            .order_by(
                Assessment.created_at.desc(),
                Assessment.id.desc(),
            )
        )

        result = await db.execute(
            stmt
        )

        rows = result.all()

        return [
            TeacherOnlineAssessmentRow(
                assessment_id=row.assessment_id,

                title=row.title,
                subject_name=(
                    row.subject_name
                    or "—"
                ),

                status=row.status,

                scheduled_at=row.scheduled_at,
                started_at=row.started_at,
                completed_at=row.completed_at,

                group_count=int(
                    row.group_count or 0
                ),

                total_students=int(
                    row.total_students or 0
                ),

                assigned_count=int(
                    row.assigned_count or 0
                ),

                in_progress_count=int(
                    row.in_progress_count or 0
                ),

                submitted_count=int(
                    row.submitted_count or 0
                ),

                completed_count=int(
                    row.completed_count or 0
                ),

                absent_count=int(
                    row.absent_count or 0
                ),

                excused_count=int(
                    row.excused_count or 0
                ),

                not_completed_count=int(
                    row.not_completed_count or 0
                ),
            )
            for row in rows
        ]
    # =====================================================
    # ASSESSMENT -> GROUPS
    # =====================================================

    @staticmethod
    async def get_groups_for_teacher(
        db: AsyncSession,
        *,
        school_id: int,
        teacher_staff_member_id: int,
        assessment_id: int,
    ) -> list[TeacherOnlineAssessmentGroupRow]:
        """
        Получить группы одного ONLINE Assessment,
        принадлежащие текущему учителю.

        Security boundary:

            school_id
            teacher_staff_member_id
            assessment_id

        Важно:

        - только AssessmentInputMode.ONLINE;
        - только текущая школа;
        - только группы текущего учителя;
        - одна строка = одна AssessmentGroup;
        - агрегаты считаются по участникам группы;
        - без lazy loading;
        - без N+1.
        """

        stmt = (
            select(
                # -----------------------------------------
                # GROUP
                # -----------------------------------------

                AssessmentGroup.id.label(
                    "assessment_group_id"
                ),

                Assessment.id.label(
                    "assessment_id"
                ),

                AssessmentGroup.school_class_id.label(
                    "school_class_id"
                ),

                func.coalesce(
                    AssessmentGroup.class_name_snapshot,
                    "",
                ).label(
                    "class_name"
                ),

                AssessmentGroup.grade_level_snapshot.label(
                    "grade_level"
                ),

                AssessmentGroup.academic_year_start_snapshot.label(
                    "academic_year_start"
                ),

                # -----------------------------------------
                # STUDENTS
                # -----------------------------------------

                func.count(
                    AssessmentStudent.id
                ).label(
                    "total_students"
                ),

                func.count(
                    case(
                        (
                            AssessmentStudent.participation_status
                            == AssessmentParticipationStatus.ASSIGNED,
                            1,
                        )
                    )
                ).label(
                    "assigned_count"
                ),

                func.count(
                    case(
                        (
                            AssessmentStudent.participation_status
                            == AssessmentParticipationStatus.IN_PROGRESS,
                            1,
                        )
                    )
                ).label(
                    "in_progress_count"
                ),

                func.count(
                    case(
                        (
                            AssessmentStudent.participation_status
                            == AssessmentParticipationStatus.SUBMITTED,
                            1,
                        )
                    )
                ).label(
                    "submitted_count"
                ),

                func.count(
                    case(
                        (
                            AssessmentStudent.participation_status
                            == AssessmentParticipationStatus.COMPLETED,
                            1,
                        )
                    )
                ).label(
                    "completed_count"
                ),

                func.count(
                    case(
                        (
                            AssessmentStudent.participation_status
                            == AssessmentParticipationStatus.ABSENT,
                            1,
                        )
                    )
                ).label(
                    "absent_count"
                ),

                func.count(
                    case(
                        (
                            AssessmentStudent.participation_status
                            == AssessmentParticipationStatus.EXCUSED,
                            1,
                        )
                    )
                ).label(
                    "excused_count"
                ),

                func.count(
                    case(
                        (
                            AssessmentStudent.participation_status
                            == AssessmentParticipationStatus.NOT_COMPLETED,
                            1,
                        )
                    )
                ).label(
                    "not_completed_count"
                ),
            )

            # =============================================
            # ASSESSMENT -> TEACHER GROUPS
            # =============================================

            .join(
                AssessmentGroup,
                (
                    AssessmentGroup.assessment_id
                    == Assessment.id
                )
                & (
                    AssessmentGroup.school_id
                    == Assessment.school_id
                ),
            )

            # =============================================
            # GROUP -> STUDENTS
            # =============================================

            .outerjoin(
                AssessmentStudent,
                (
                    AssessmentStudent.assessment_group_id
                    == AssessmentGroup.id
                )
                & (
                    AssessmentStudent.school_id
                    == AssessmentGroup.school_id
                ),
            )

            # =============================================
            # SECURITY / ONLINE
            # =============================================

            .where(
                Assessment.id
                == assessment_id,

                Assessment.school_id
                == school_id,

                Assessment.input_mode
                == AssessmentInputMode.ONLINE,

                AssessmentGroup.school_id
                == school_id,

                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,
            )

            # =============================================
            # GROUP BY
            # =============================================

            .group_by(
                AssessmentGroup.id,
                Assessment.id,
                AssessmentGroup.school_class_id,
                AssessmentGroup.class_name_snapshot,
                AssessmentGroup.grade_level_snapshot,
                AssessmentGroup.academic_year_start_snapshot,
            )

            # =============================================
            # ORDER
            # =============================================

            .order_by(
                AssessmentGroup.grade_level_snapshot.asc(),
                AssessmentGroup.class_name_snapshot.asc(),
                AssessmentGroup.id.asc(),
            )
        )

        result = await db.execute(
            stmt
        )

        rows = result.all()

        return [
            TeacherOnlineAssessmentGroupRow(
                assessment_group_id=(
                    row.assessment_group_id
                ),

                assessment_id=(
                    row.assessment_id
                ),

                school_class_id=(
                    row.school_class_id
                ),

                class_name=(
                    row.class_name
                    or "—"
                ),

                grade_level=(
                    row.grade_level
                ),

                academic_year_start=(
                    row.academic_year_start
                ),

                total_students=int(
                    row.total_students or 0
                ),

                assigned_count=int(
                    row.assigned_count or 0
                ),

                in_progress_count=int(
                    row.in_progress_count or 0
                ),

                submitted_count=int(
                    row.submitted_count or 0
                ),

                completed_count=int(
                    row.completed_count or 0
                ),

                absent_count=int(
                    row.absent_count or 0
                ),

                excused_count=int(
                    row.excused_count or 0
                ),

                not_completed_count=int(
                    row.not_completed_count or 0
                ),
            )
            for row in rows
        ]

    # =====================================================
    # GROUP HEADER
    # =====================================================

    @staticmethod
    async def get_group_header_for_teacher(
        db: AsyncSession,
        *,
        school_id: int,
        teacher_staff_member_id: int,
        assessment_group_id: int,
    ) -> TeacherOnlineAssessmentGroupHeaderRow | None:
        """
        Получить метаданные одной группы ONLINE Assessment.

        Security boundary:

            school_id
            teacher_staff_member_id
            assessment_group_id

        Возвращает None если:

            - группа не существует;
            - принадлежит другому учителю;
            - принадлежит другой школе;
            - Assessment не ONLINE.
        """

        stmt = (
            select(
                AssessmentGroup.id.label(
                    "assessment_group_id"
                ),

                Assessment.id.label(
                    "assessment_id"
                ),

                AssessmentGroup.school_class_id.label(
                    "school_class_id"
                ),

                AssessmentGroup.class_name_snapshot.label(
                    "class_name"
                ),

                AssessmentGroup.grade_level_snapshot.label(
                    "grade_level"
                ),

                AssessmentGroup.academic_year_start_snapshot.label(
                    "academic_year_start"
                ),
            )
            .join(
                Assessment,
                Assessment.id
                == AssessmentGroup.assessment_id,
            )
            .where(
                AssessmentGroup.id
                == assessment_group_id,

                AssessmentGroup.school_id
                == school_id,

                Assessment.school_id
                == school_id,

                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,

                Assessment.input_mode
                == AssessmentInputMode.ONLINE,
            )
        )

        result = await db.execute(stmt)

        row = result.one_or_none()

        if row is None:
            return None

        return TeacherOnlineAssessmentGroupHeaderRow(
            assessment_group_id=row.assessment_group_id,
            assessment_id=row.assessment_id,

            school_class_id=row.school_class_id,
            class_name=row.class_name,

            grade_level=row.grade_level,
            academic_year_start=row.academic_year_start,
        )

    # =====================================================
    # GROUP -> STUDENTS
    # =====================================================

    @staticmethod
    async def get_students_for_teacher(
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            assessment_group_id: int,
    ) -> list[TeacherOnlineAssessmentStudentRow]:
        """
        Получить участников одной группы ONLINE Assessment,
        принадлежащей текущему учителю.

        Security boundary:

            school_id
            teacher_staff_member_id
            assessment_group_id

        Важно:

        - только AssessmentInputMode.ONLINE;
        - только текущая школа;
        - только группа текущего учителя;
        - одна строка = один AssessmentStudent;
        - итог AssessmentResult загружается тем же SQL;
        - AssessmentResult может отсутствовать;
        - без lazy loading;
        - без N+1.
        """

        stmt = (
            select(
                # -----------------------------------------
                # STUDENT PARTICIPATION
                # -----------------------------------------

                AssessmentStudent.id.label(
                    "assessment_student_id"
                ),

                AssessmentGroup.id.label(
                    "assessment_group_id"
                ),

                Assessment.id.label(
                    "assessment_id"
                ),

                AssessmentStudent.student_id.label(
                    "student_id"
                ),

                func.coalesce(
                    AssessmentStudent.student_name_snapshot,
                    "",
                ).label(
                    "student_name"
                ),

                AssessmentStudent.participation_status.label(
                    "participation_status"
                ),

                AssessmentStudent.assigned_at.label(
                    "assigned_at"
                ),

                AssessmentStudent.started_at.label(
                    "started_at"
                ),

                AssessmentStudent.completed_at.label(
                    "completed_at"
                ),

                # -----------------------------------------
                # FINAL RESULT
                # -----------------------------------------

                AssessmentResult.score.label(
                    "result_score"
                ),

                AssessmentResult.max_score.label(
                    "result_max_score"
                ),

                AssessmentResult.percent.label(
                    "result_percent"
                ),

                AssessmentResult.grade.label(
                    "result_grade"
                ),
            )

            # =============================================
            # ASSESSMENT -> TEACHER GROUP
            # =============================================

            .join(
                AssessmentGroup,
                (
                        AssessmentGroup.assessment_id
                        == Assessment.id
                )
                & (
                        AssessmentGroup.school_id
                        == Assessment.school_id
                ),
            )

            # =============================================
            # GROUP -> STUDENTS
            # =============================================

            .join(
                AssessmentStudent,
                (
                        AssessmentStudent.assessment_group_id
                        == AssessmentGroup.id
                )
                & (
                        AssessmentStudent.school_id
                        == AssessmentGroup.school_id
                ),
            )

            # =============================================
            # STUDENT -> FINAL RESULT
            # =============================================

            .outerjoin(
                AssessmentResult,
                AssessmentResult.assessment_student_id
                == AssessmentStudent.id,
            )

            # =============================================
            # SECURITY / ONLINE
            # =============================================

            .where(
                Assessment.school_id
                == school_id,

                Assessment.input_mode
                == AssessmentInputMode.ONLINE,

                AssessmentGroup.id
                == assessment_group_id,

                AssessmentGroup.school_id
                == school_id,

                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,

                AssessmentStudent.school_id
                == school_id,
            )

            # =============================================
            # ORDER
            # =============================================

            .order_by(
                AssessmentStudent.student_name_snapshot.asc(),
                AssessmentStudent.student_id.asc(),
                AssessmentStudent.id.asc(),
            )
        )

        result = await db.execute(
            stmt
        )

        rows = result.all()

        return [
            TeacherOnlineAssessmentStudentRow(
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
                        or "—"
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
        ]
