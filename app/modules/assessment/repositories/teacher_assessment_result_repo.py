# app/modules/assessment/repositories/teacher_assessment_result_repo.py

from __future__ import annotations
from app.modules.assessment.repositories.assessment_name_columns import title_column

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, func, case, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager

from app.modules.assessment.enums import (
    AssessmentAnswerStatus,
    AssessmentGrade,
    AssessmentParticipationStatus,
    AssessmentQuestionType, AssessmentInputMode,
)
from app.modules.assessment.models import (
    Assessment,
    AssessmentGroup,
    AssessmentResult,
    AssessmentStudent,
    AssessmentObjectiveResult,
    AssessmentObjective,
    AssessmentQuestion,
    AssessmentStudentAnswer,
)


# =========================================================
# READ ROWS
# =========================================================


@dataclass(frozen=True, slots=True)
class TeacherClassAssessmentRow:
    """
    Один Assessment конкретного класса,
    доступный текущему учителю.
    """

    assessment_id: int
    assessment_group_id: int

    title: str
    subject_name: str

    school_class_id: int
    class_name: str
    grade_level: int

    max_score: Decimal | None

    total_students: int
    participated_students: int


@dataclass(frozen=True, slots=True)
class TeacherStudentResultRow:
    """
    Один ученик внутри конкретной AssessmentGroup.
    """

    assessment_id: int
    assessment_group_id: int

    assessment_title: str
    subject_name: str
    assessment_input_mode: AssessmentInputMode

    school_class_id: int
    class_name: str
    grade_level: int

    assessment_max_score: Decimal | None

    assessment_student_id: int
    student_id: int
    student_name: str

    participation_status: AssessmentParticipationStatus

    score: Decimal | None
    max_score: Decimal | None
    percent: Decimal | None
    grade: AssessmentGrade | None


@dataclass(frozen=True, slots=True)
class TeacherObjectiveSummaryRow:
    """
    Агрегированный результат одной учебной цели
    внутри конкретной AssessmentGroup.

    Одна строка =
        AssessmentGroup + AssessmentObjective.

    score_sum / max_score_sum нужны
    для корректного weighted aggregation.

    mastery_percent =
        score_sum / max_score_sum * 100.
    """

    assessment_id: int
    assessment_group_id: int

    assessment_title: str
    subject_name: str

    school_class_id: int
    class_name: str
    grade_level: int

    assessment_objective_id: int
    learning_objective_id: int

    objective_code: str
    objective_title: str
    order_no: int

    objective_max_score: Decimal

    participated_students: int

    score_sum: Decimal
    max_score_sum: Decimal

    mastery_percent: Decimal | None


@dataclass(frozen=True, slots=True)
class TeacherObjectiveStudentRow:
    """
    Результат одного ученика
    по одной учебной цели.
    """

    assessment_id: int
    assessment_group_id: int

    assessment_title: str
    subject_name: str

    school_class_id: int
    class_name: str
    grade_level: int

    assessment_objective_id: int
    learning_objective_id: int

    objective_code: str
    objective_title: str
    objective_max_score: Decimal

    assessment_student_id: int
    student_id: int
    student_name: str

    participation_status: AssessmentParticipationStatus

    score: Decimal | None
    max_score: Decimal | None
    percent: Decimal | None


@dataclass(frozen=True, slots=True)
class TeacherStudentAnswerRow:
    """
    Ответ ученика, доступный текущему учителю для просмотра/проверки.

    Repository возвращает только данные и обеспечивает security boundary.
    Решение о возможности ручной проверки принимает Service Layer.
    """

    assessment_id: int
    assessment_group_id: int
    assessment_student_id: int

    student_id: int
    student_name: str

    answer_id: int
    question_id: int
    question_type: AssessmentQuestionType
    question_text: str
    question_order_no: int

    answer_data: dict
    status: AssessmentAnswerStatus

    score: Decimal | None
    max_score: Decimal
    is_correct: bool | None

    checked_by_user_id: int | None
    checked_at: datetime | None
    content: dict | None = None
    answer_key: dict | None = None
    grading_settings: dict | None = None
    diagnostic_snapshot: dict | None = None
    instruction: str | None = None


@dataclass(frozen=True, slots=True)
class TeacherStudentReviewHeaderRow:
    """
    Заголовок страницы просмотра ответов ученика.

    Содержит:
        - идентификацию Assessment / Group / Student;
        - текущий статус участия;
        - итоговый AssessmentResult, если он уже сформирован.

    AssessmentResult может отсутствовать,
    пока работа ожидает ручной проверки.
    """

    assessment_id: int
    assessment_group_id: int
    assessment_student_id: int

    student_id: int
    student_name: str

    participation_status: AssessmentParticipationStatus

    score: Decimal | None
    max_score: Decimal | None
    percent: Decimal | None
    grade: AssessmentGrade | None


class TeacherAssessmentResultRepo:
    """
    Read-repository teacher drill-down.

    Назначение:
        teacher
          -> class
          -> assessments
          -> students/results

    Не выполняет:
        - создание AssessmentResult;
        - изменение AssessmentResult;
        - пересчёт оценок;
        - commit.

    Security boundary всегда включает:
        school_id
        teacher_staff_member_id
    """

    @staticmethod
    def _work_group_ids(*, school_id, teacher_staff_member_id, assessment_group_id):
        """Authorized logical work: diagnostic subject + class + year.

        A normal/manual assessment stays a single group. The seed is itself
        school/teacher scoped, so guessing another teacher's group grants nothing.
        SQL subquery, never one query per variant. No records are rewritten.
        """
        a = Assessment.__table__
        g = AssessmentGroup.__table__
        seed_a = a.alias('work_seed_assessment')
        seed_g = g.alias('work_seed_group')
        same_work = or_(g.c.id == seed_g.c.id, and_(
            seed_a.c.diagnostic_subject_id.is_not(None),
            a.c.diagnostic_subject_id == seed_a.c.diagnostic_subject_id,
            a.c.subject_id == seed_a.c.subject_id,
            g.c.school_class_id == seed_g.c.school_class_id,
            g.c.academic_year_start_snapshot == seed_g.c.academic_year_start_snapshot,
        ))
        return (select(g.c.id).select_from(
            seed_g.join(seed_a, seed_a.c.id == seed_g.c.assessment_id)
            .join(g.join(a, a.c.id == g.c.assessment_id), same_work))
            .where(seed_g.c.id == assessment_group_id,
                seed_g.c.school_id == school_id, seed_a.c.school_id == school_id,
                seed_g.c.teacher_staff_member_id == teacher_staff_member_id,
                g.c.school_id == school_id, a.c.school_id == school_id,
                g.c.teacher_staff_member_id == teacher_staff_member_id))

    @staticmethod
    async def get_teacher_student_review_header(
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            assessment_student_id: int,
    ) -> TeacherStudentReviewHeaderRow | None:
        """
        Получить заголовок страницы просмотра ответов
        конкретного участника ONLINE Assessment.

        Security boundary:
            school_id
            teacher_staff_member_id
            assessment_student_id

        LEFT JOIN AssessmentResult обязателен:
        участник со статусом SUBMITTED ещё может
        не иметь итогового AssessmentResult.

        Один SQL-запрос.
        """

        stmt = (
            select(
                Assessment.id.label(
                    "assessment_id"
                ),

                AssessmentGroup.id.label(
                    "assessment_group_id"
                ),

                AssessmentStudent.id.label(
                    "assessment_student_id"
                ),

                AssessmentStudent.student_id.label(
                    "student_id"
                ),

                AssessmentStudent.student_name_snapshot.label(
                    "student_name"
                ),

                AssessmentStudent.participation_status.label(
                    "participation_status"
                ),

                AssessmentResult.score.label(
                    "score"
                ),

                AssessmentResult.max_score.label(
                    "result_max_score"
                ),

                AssessmentResult.percent.label(
                    "percent"
                ),

                AssessmentResult.grade.label(
                    "grade"
                ),
            )
            .select_from(
                AssessmentStudent
            )
            .join(
                AssessmentGroup,
                AssessmentGroup.id
                == AssessmentStudent.assessment_group_id,
            )
            .join(
                Assessment,
                Assessment.id
                == AssessmentGroup.assessment_id,
            )
            .outerjoin(
                AssessmentResult,
                AssessmentResult.assessment_student_id
                == AssessmentStudent.id,
            )
            .where(
                AssessmentStudent.id
                == assessment_student_id,

                AssessmentStudent.school_id
                == school_id,

                AssessmentGroup.school_id
                == school_id,

                Assessment.school_id
                == school_id,

                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,
            )
        )

        result = await db.execute(
            stmt
        )

        row = result.one_or_none()

        if row is None:
            return None

        return TeacherStudentReviewHeaderRow(
            assessment_id=int(
                row.assessment_id
            ),

            assessment_group_id=int(
                row.assessment_group_id
            ),

            assessment_student_id=int(
                row.assessment_student_id
            ),

            student_id=int(
                row.student_id
            ),

            student_name=(
                    row.student_name
                    or f"ID {row.student_id}"
            ),

            participation_status=(
                row.participation_status
            ),

            score=row.score,

            max_score=(
                row.result_max_score
            ),

            percent=row.percent,

            grade=row.grade,
        )

    # =====================================================
    # TEACHER REVIEW -> STUDENT ANSWERS
    # =====================================================

    @staticmethod
    async def get_teacher_student_answers(
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            assessment_student_id: int,
    ) -> list[TeacherStudentAnswerRow]:
        """
        Получить все сохранённые ответы конкретного участника,
        доступные текущему учителю.

        Security boundary:
            school_id
            teacher_staff_member_id
            assessment_student_id

        Дополнительно проверяется принадлежность:
            AssessmentStudent -> AssessmentGroup -> Assessment
            AssessmentStudentAnswer -> AssessmentQuestion -> Assessment.
        """

        stmt = (
            select(
                Assessment.id.label("assessment_id"),
                AssessmentGroup.id.label("assessment_group_id"),
                AssessmentStudent.id.label("assessment_student_id"),
                AssessmentStudent.student_id.label("student_id"),
                AssessmentStudent.student_name_snapshot.label("student_name"),

                AssessmentStudentAnswer.id.label("answer_id"),
                AssessmentStudentAnswer.question_id.label("question_id"),
                AssessmentStudentAnswer.answer_data.label("answer_data"),
                AssessmentStudentAnswer.status.label("answer_status"),
                AssessmentStudentAnswer.score.label("score"),
                AssessmentStudentAnswer.max_score.label("answer_max_score"),
                AssessmentStudentAnswer.is_correct.label("is_correct"),
                AssessmentStudentAnswer.checked_by_user_id.label(
                    "checked_by_user_id"
                ),
                AssessmentStudentAnswer.checked_at.label("checked_at"),

                AssessmentQuestion.question_type.label("question_type"),
                AssessmentQuestion.text.label("question_text"),
                AssessmentQuestion.content.label("question_content"),
                AssessmentQuestion.answer_key.label("question_answer_key"),
                AssessmentQuestion.grading_settings.label("question_grading"),
                AssessmentQuestion.diagnostic_snapshot.label("question_snapshot"),
                AssessmentQuestion.instruction.label("question_instruction"),
                AssessmentQuestion.order_no.label("question_order_no"),
            )
            .select_from(AssessmentStudent)
            .join(
                AssessmentGroup,
                AssessmentGroup.id
                == AssessmentStudent.assessment_group_id,
            )
            .join(
                Assessment,
                Assessment.id
                == AssessmentGroup.assessment_id,
            )
            .join(
                AssessmentStudentAnswer,
                AssessmentStudentAnswer.assessment_student_id
                == AssessmentStudent.id,
            )
            .join(
                AssessmentQuestion,
                (
                    AssessmentQuestion.id
                    == AssessmentStudentAnswer.question_id
                )
                & (
                    AssessmentQuestion.assessment_id
                    == Assessment.id
                ),
            )
            .where(
                AssessmentStudent.id == assessment_student_id,

                AssessmentStudent.school_id == school_id,
                AssessmentGroup.school_id == school_id,
                Assessment.school_id == school_id,

                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,
            )
            .order_by(
                AssessmentQuestion.order_no.asc(),
                AssessmentQuestion.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return [
            TeacherStudentAnswerRow(
                assessment_id=int(row.assessment_id),
                assessment_group_id=int(row.assessment_group_id),
                assessment_student_id=int(row.assessment_student_id),

                student_id=int(row.student_id),
                student_name=(
                    row.student_name
                    or f"ID {row.student_id}"
                ),

                answer_id=int(row.answer_id),
                question_id=int(row.question_id),
                question_type=row.question_type,
                question_text=row.question_text,
                content=row.question_content,
                answer_key=row.question_answer_key,
                grading_settings=row.question_grading,
                diagnostic_snapshot=row.question_snapshot,
                instruction=row.question_instruction,
                question_order_no=int(row.question_order_no),

                answer_data=row.answer_data or {},
                status=row.answer_status,

                score=row.score,
                max_score=row.answer_max_score,
                is_correct=row.is_correct,

                checked_by_user_id=row.checked_by_user_id,
                checked_at=row.checked_at,
            )
            for row in result.all()
        ]

    @staticmethod
    async def get_teacher_answer_for_review(
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            assessment_student_answer_id: int,
    ) -> AssessmentStudentAnswer | None:
        """
        Получить ORM-ответ ученика для операции ручной проверки.

        Security boundary:
            school_id
            teacher_staff_member_id
            assessment_student_answer_id

        Одним SQL-запросом загружаются:
            AssessmentStudentAnswer
            -> AssessmentStudent
            -> AssessmentGroup
            -> Assessment

        Это позволяет Service Layer безопасно обращаться к relationship
        при lazy="raise" без дополнительных SELECT и без N+1.

        Возвращается ORM AssessmentStudentAnswer, потому что
        Service Layer должен изменить score/status/check metadata
        внутри своей транзакции.

        Repository не решает:
            - можно ли проверять текущий status;
            - допустим ли выставленный score;
            - когда завершать AssessmentStudent;
            - когда создавать AssessmentResult.
        """

        stmt = (
            select(AssessmentStudentAnswer)
            .join(
                AssessmentStudent,
                AssessmentStudent.id
                == AssessmentStudentAnswer.assessment_student_id,
            )
            .join(
                AssessmentGroup,
                AssessmentGroup.id
                == AssessmentStudent.assessment_group_id,
            )
            .join(
                Assessment,
                Assessment.id
                == AssessmentGroup.assessment_id,
            )
            .join(
                AssessmentQuestion,
                (
                        AssessmentQuestion.id
                        == AssessmentStudentAnswer.question_id
                )
                & (
                        AssessmentQuestion.assessment_id
                        == Assessment.id
                ),
            )
            .options(
                contains_eager(
                    AssessmentStudentAnswer.assessment_student
                )
                .contains_eager(
                    AssessmentStudent.assessment_group
                )
                .contains_eager(
                    AssessmentGroup.assessment
                )
            )
            .where(
                AssessmentStudentAnswer.id
                == assessment_student_answer_id,

                AssessmentStudent.school_id == school_id,
                AssessmentGroup.school_id == school_id,
                Assessment.school_id == school_id,

                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,
            )
        )

        result = await db.execute(stmt)

        return result.unique().scalar_one_or_none()

    # =====================================================
    # TEACHER CLASS -> ASSESSMENTS
    # =====================================================

    @staticmethod
    async def get_teacher_class_assessments(
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            school_class_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
    ) -> list[TeacherClassAssessmentRow]:
        """
        Получить Assessment текущего учителя
        для конкретного класса.

        Одна сессия/предмет/класс = одна строка; ручная работа самостоятельна.

        total_students и participated_students
        рассчитываются в этом же SQL-запросе.

        Security boundary:
            school_id
            teacher_staff_member_id
            school_class_id
        """

        stmt = (
            select(
                func.min(Assessment.id).label(
                    "assessment_id"
                ),

                func.min(AssessmentGroup.id).label(
                    "assessment_group_id"
                ),

                func.min(title_column()).label(
                    "title"
                ),

                func.min(Assessment.subject_name_snapshot).label(
                    "subject_name"
                ),

                AssessmentGroup.school_class_id.label(
                    "school_class_id"
                ),

                func.min(AssessmentGroup.class_name_snapshot).label(
                    "class_name"
                ),

                func.min(AssessmentGroup.grade_level_snapshot).label(
                    "grade_level"
                ),

                func.max(Assessment.max_score).label(
                    "max_score"
                ),

                func.count(
                    func.distinct(AssessmentStudent.student_id)
                ).label(
                    "total_students"
                ),

                func.count(
                    func.distinct(case(
                        (
                            AssessmentStudent.participation_status
                            == AssessmentParticipationStatus.COMPLETED,
                            AssessmentStudent.student_id,
                        ),
                        else_=None,
                    ))
                ).label(
                    "participated_students"
                ),
            )
            .select_from(
                AssessmentGroup
            )
            .join(
                Assessment,
                Assessment.id
                == AssessmentGroup.assessment_id,
            )
            .outerjoin(
                AssessmentStudent,
                AssessmentStudent.assessment_group_id
                == AssessmentGroup.id,
            )
            .where(
                AssessmentGroup.school_id
                == school_id,

                Assessment.school_id
                == school_id,

                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,

                AssessmentGroup.school_class_id
                == school_class_id,
            )
        )

        # =====================================================
        # FILTERS
        # =====================================================

        if academic_year_start is not None:
            stmt = stmt.where(
                AssessmentGroup
                .academic_year_start_snapshot
                == academic_year_start
            )

        if subject_id is not None:
            stmt = stmt.where(
                Assessment.subject_id
                == subject_id
            )

        # =====================================================
        # GROUP / ORDER
        # =====================================================

        stmt = (
            stmt
            .group_by(
                func.coalesce(Assessment.diagnostic_subject_id, -Assessment.id),
                Assessment.subject_id, AssessmentGroup.school_class_id,
                AssessmentGroup.academic_year_start_snapshot,
            )
            .order_by(func.min(case(*[(Assessment.checkpoint == name, index) for index,name in enumerate(
                ('baseline','quarter_1','quarter_2','quarter_3','quarter_4','final'))], else_=6)).asc(),
                      func.max(Assessment.created_at).asc(),
                      func.min(Assessment.id).desc(), func.min(AssessmentGroup.id).desc())
        )

        # =====================================================
        # EXECUTE
        # =====================================================

        result = await db.execute(
            stmt
        )

        rows = result.all()

        return [
            TeacherClassAssessmentRow(
                assessment_id=int(
                    row.assessment_id
                ),

                assessment_group_id=int(
                    row.assessment_group_id
                ),

                title=(
                        row.title
                        or f"Assessment #{row.assessment_id}"
                ),

                subject_name=(
                        row.subject_name
                        or "—"
                ),

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

                max_score=(
                    row.max_score
                ),

                total_students=int(
                    row.total_students or 0
                ),

                participated_students=int(
                    row.participated_students or 0
                ),
            )
            for row in rows
        ]

    # =====================================================
    # ASSESSMENT GROUP -> STUDENTS
    # =====================================================

    @staticmethod
    async def get_teacher_group_student_rows(
        db: AsyncSession,
        *,
        school_id: int,
        teacher_staff_member_id: int,
        assessment_group_id: int,
    ) -> list[TeacherStudentResultRow]:
        """
        Получить результаты всех учеников
        конкретной AssessmentGroup.

        LEFT JOIN AssessmentResult обязателен:
        ABSENT / EXCUSED / NOT_COMPLETED могут
        законно не иметь итогового результата.
        """

        stmt = (
            select(
                Assessment.id.label(
                    "assessment_id"
                ),

                title_column().label(
                    "assessment_title"
                ),

                Assessment.subject_name_snapshot.label(
                    "subject_name"
                ),

                Assessment.input_mode.label(
                    "assessment_input_mode"
                ),

                Assessment.max_score.label(
                    "assessment_max_score"
                ),

                AssessmentGroup.id.label(
                    "assessment_group_id"
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

                AssessmentStudent.id.label(
                    "assessment_student_id"
                ),

                AssessmentStudent.student_id.label(
                    "student_id"
                ),

                AssessmentStudent.student_name_snapshot.label(
                    "student_name"
                ),

                AssessmentStudent.participation_status.label(
                    "participation_status"
                ),

                AssessmentResult.score.label(
                    "score"
                ),

                AssessmentResult.max_score.label(
                    "result_max_score"
                ),

                AssessmentResult.percent.label(
                    "percent"
                ),

                AssessmentResult.grade.label(
                    "grade"
                ),
            )
            .select_from(
                AssessmentGroup
            )
            .join(
                Assessment,
                Assessment.id
                == AssessmentGroup.assessment_id,
            )
            .join(
                AssessmentStudent,
                AssessmentStudent.assessment_group_id
                == AssessmentGroup.id,
            )
            .outerjoin(
                AssessmentResult,
                AssessmentResult.assessment_student_id
                == AssessmentStudent.id,
            )
            .where(
                AssessmentGroup.id.in_(TeacherAssessmentResultRepo._work_group_ids(
                    school_id=school_id,
                    teacher_staff_member_id=teacher_staff_member_id,
                    assessment_group_id=assessment_group_id,
                )),

                AssessmentGroup.school_id
                == school_id,

                Assessment.school_id
                == school_id,

                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,
            )
            .order_by(
                AssessmentStudent.student_name_snapshot.asc(),
                AssessmentStudent.id.asc(),
            )
        )

        result = await db.execute(
            stmt
        )

        rows = result.all()

        return [
            TeacherStudentResultRow(
                assessment_id=int(
                    row.assessment_id
                ),

                assessment_group_id=int(
                    row.assessment_group_id
                ),

                assessment_title=(
                    row.assessment_title
                    or f"Assessment #{row.assessment_id}"
                ),

                subject_name=(
                    row.subject_name
                    or "—"
                ),

                assessment_input_mode=(
                    row.assessment_input_mode
                ),

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

                assessment_max_score=(
                    row.assessment_max_score
                ),

                assessment_student_id=int(
                    row.assessment_student_id
                ),

                student_id=int(
                    row.student_id
                ),

                student_name=(
                    row.student_name
                    or f"ID {row.student_id}"
                ),

                participation_status=(
                    row.participation_status
                ),

                score=row.score,

                max_score=(
                    row.result_max_score
                ),

                percent=row.percent,

                grade=row.grade,
            )
            for row in rows
        ]

    # =====================================================
    # ASSESSMENT GROUP -> OBJECTIVE SUMMARY
    # =====================================================

    @staticmethod
    async def get_teacher_group_objective_summary(
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            assessment_group_id: int,
    ) -> list[TeacherObjectiveSummaryRow]:
        """
        Получить аналитику учебных целей
        конкретной AssessmentGroup.

        Один SQL-запрос.

        Одна строка =
            одна AssessmentObjective.

        Security boundary:
            school_id
            teacher_staff_member_id
            assessment_group_id

        В расчёт входят только реальные
        AssessmentObjectiveResult.

        Поэтому ABSENT / EXCUSED /
        NOT_COMPLETED автоматически
        не искажают показатели.

        mastery_percent рассчитывается
        через агрегированные суммы:

            SUM(score)
            /
            SUM(max_score)
            * 100

        Нельзя использовать AVG(percent)
        как основной показатель.
        """

        score_sum_expr = func.coalesce(
            func.sum(
                AssessmentObjectiveResult.score
            ),
            0,
        )

        max_score_sum_expr = func.coalesce(
            func.sum(
                AssessmentObjectiveResult.max_score
            ),
            0,
        )

        participated_students_expr = func.count(
            func.distinct(
                case((AssessmentObjectiveResult.id.is_not(None), AssessmentStudent.student_id), else_=None)
            )
        )

        mastery_percent_expr = case(
            (
                max_score_sum_expr > 0,
                (
                        score_sum_expr
                        * Decimal("100")
                        / max_score_sum_expr
                ),
            ),
            else_=None,
        )

        stmt = (
            select(
                func.min(Assessment.id).label(
                    "assessment_id"
                ),

                func.min(AssessmentGroup.id).label(
                    "assessment_group_id"
                ),

                func.min(title_column()).label(
                    "assessment_title"
                ),

                func.min(Assessment.subject_name_snapshot).label(
                    "subject_name"
                ),

                AssessmentGroup.school_class_id.label(
                    "school_class_id"
                ),

                func.min(AssessmentGroup.class_name_snapshot).label(
                    "class_name"
                ),

                func.min(AssessmentGroup.grade_level_snapshot).label(
                    "grade_level"
                ),

                func.min(AssessmentObjective.id).label(
                    "assessment_objective_id"
                ),

                AssessmentObjective.learning_objective_id.label(
                    "learning_objective_id"
                ),

                func.min(AssessmentObjective.code_snapshot).label(
                    "objective_code"
                ),

                func.min(AssessmentObjective.title_snapshot).label(
                    "objective_title"
                ),

                func.min(AssessmentObjective.order_no).label(
                    "order_no"
                ),

                func.max(AssessmentObjective.max_score).label(
                    "objective_max_score"
                ),

                participated_students_expr.label(
                    "participated_students"
                ),

                score_sum_expr.label(
                    "score_sum"
                ),

                max_score_sum_expr.label(
                    "max_score_sum"
                ),

                mastery_percent_expr.label(
                    "mastery_percent"
                ),
            )
            .select_from(
                AssessmentGroup
            )
            .join(
                Assessment,
                Assessment.id
                == AssessmentGroup.assessment_id,
            )
            .join(
                AssessmentObjective,
                AssessmentObjective.assessment_id
                == Assessment.id,
            )
            .outerjoin(
                AssessmentStudent,
                AssessmentStudent.assessment_group_id
                == AssessmentGroup.id,
            )
            .outerjoin(
                AssessmentResult,
                AssessmentResult.assessment_student_id
                == AssessmentStudent.id,
            )
            .outerjoin(
                AssessmentObjectiveResult,
                (
                        AssessmentObjectiveResult.assessment_result_id
                        == AssessmentResult.id
                )
                & (
                        AssessmentObjectiveResult.assessment_objective_id
                        == AssessmentObjective.id
                ),
            )
            .where(
                AssessmentGroup.id.in_(TeacherAssessmentResultRepo._work_group_ids(
                    school_id=school_id,
                    teacher_staff_member_id=teacher_staff_member_id,
                    assessment_group_id=assessment_group_id,
                )),

                AssessmentGroup.school_id
                == school_id,

                Assessment.school_id
                == school_id,

                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,
            )
            .group_by(
                Assessment.subject_id, AssessmentGroup.school_class_id,
                AssessmentObjective.learning_objective_id,
            )
            .order_by(func.min(AssessmentObjective.order_no).asc(),
                      AssessmentObjective.learning_objective_id.asc())
        )

        result = await db.execute(
            stmt
        )

        rows = result.all()

        return [
            TeacherObjectiveSummaryRow(
                assessment_id=int(
                    row.assessment_id
                ),

                assessment_group_id=int(
                    row.assessment_group_id
                ),

                assessment_title=(
                        row.assessment_title
                        or f"Assessment #{row.assessment_id}"
                ),

                subject_name=(
                        row.subject_name
                        or "—"
                ),

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

                assessment_objective_id=int(
                    row.assessment_objective_id
                ),

                learning_objective_id=int(
                    row.learning_objective_id
                ),

                objective_code=(
                        row.objective_code
                        or "—"
                ),

                objective_title=(
                        row.objective_title
                        or "—"
                ),

                order_no=int(
                    row.order_no
                ),

                objective_max_score=(
                    row.objective_max_score
                ),

                participated_students=int(
                    row.participated_students or 0
                ),

                score_sum=Decimal(
                    row.score_sum or 0
                ),

                max_score_sum=Decimal(
                    row.max_score_sum or 0
                ),

                mastery_percent=(
                    row.mastery_percent
                    if row.mastery_percent is not None
                    else None
                ),
            )
            for row in rows
        ]

    # =====================================================
    # OBJECTIVE -> STUDENTS
    # =====================================================

    @staticmethod
    async def get_teacher_objective_student_rows(
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            assessment_group_id: int,
            assessment_objective_id: int,
    ) -> list[TeacherObjectiveStudentRow]:
        """
        Получить учеников конкретной группы
        и результаты по одной учебной цели.

        LEFT JOIN обязателен:

            ABSENT
            EXCUSED
            NOT_COMPLETED

        законно могут не иметь
        AssessmentResult /
        AssessmentObjectiveResult.

        Security boundary:
            school_id
            teacher_staff_member_id
            assessment_group_id

        Дополнительно проверяется, что
        AssessmentObjective принадлежит
        тому же Assessment.
        """

        stmt = (
            select(
                Assessment.id.label(
                    "assessment_id"
                ),

                AssessmentGroup.id.label(
                    "assessment_group_id"
                ),

                title_column().label(
                    "assessment_title"
                ),

                Assessment.subject_name_snapshot.label(
                    "subject_name"
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

                AssessmentObjective.id.label(
                    "assessment_objective_id"
                ),

                AssessmentObjective.learning_objective_id.label(
                    "learning_objective_id"
                ),

                AssessmentObjective.code_snapshot.label(
                    "objective_code"
                ),

                AssessmentObjective.title_snapshot.label(
                    "objective_title"
                ),

                AssessmentObjective.max_score.label(
                    "objective_max_score"
                ),

                AssessmentStudent.id.label(
                    "assessment_student_id"
                ),

                AssessmentStudent.student_id.label(
                    "student_id"
                ),

                AssessmentStudent.student_name_snapshot.label(
                    "student_name"
                ),

                AssessmentStudent.participation_status.label(
                    "participation_status"
                ),

                AssessmentObjectiveResult.score.label(
                    "score"
                ),

                AssessmentObjectiveResult.max_score.label(
                    "result_max_score"
                ),

                AssessmentObjectiveResult.percent.label(
                    "percent"
                ),
            )
            .select_from(
                AssessmentGroup
            )
            .join(
                Assessment,
                Assessment.id
                == AssessmentGroup.assessment_id,
            )
            .join(
                AssessmentObjective,
                (
                        AssessmentObjective.assessment_id
                        == Assessment.id
                )
                & (
                        AssessmentObjective.learning_objective_id
                        == select(AssessmentObjective.__table__.c.learning_objective_id)
                        .where(
                            AssessmentObjective.__table__.c.id == assessment_objective_id,
                            AssessmentObjective.__table__.c.assessment_id.in_(
                                select(AssessmentGroup.__table__.c.assessment_id).where(
                                    AssessmentGroup.__table__.c.id.in_(
                                        TeacherAssessmentResultRepo._work_group_ids(
                                            school_id=school_id,
                                            teacher_staff_member_id=teacher_staff_member_id,
                                            assessment_group_id=assessment_group_id,
                                        )
                                    )
                                )
                            ),
                        ).correlate(None).scalar_subquery()
                ),
            )
            .join(
                AssessmentStudent,
                AssessmentStudent.assessment_group_id
                == AssessmentGroup.id,
            )
            .outerjoin(
                AssessmentResult,
                AssessmentResult.assessment_student_id
                == AssessmentStudent.id,
            )
            .outerjoin(
                AssessmentObjectiveResult,
                (
                        AssessmentObjectiveResult.assessment_result_id
                        == AssessmentResult.id
                )
                & (
                        AssessmentObjectiveResult.assessment_objective_id
                        == AssessmentObjective.id
                ),
            )
            .where(
                AssessmentGroup.id.in_(TeacherAssessmentResultRepo._work_group_ids(
                    school_id=school_id,
                    teacher_staff_member_id=teacher_staff_member_id,
                    assessment_group_id=assessment_group_id,
                )),

                AssessmentGroup.school_id
                == school_id,

                Assessment.school_id
                == school_id,

                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,
            )
            .order_by(
                AssessmentStudent.student_name_snapshot.asc(),
                AssessmentStudent.id.asc(),
            )
        )

        result = await db.execute(
            stmt
        )

        rows = result.all()

        return [
            TeacherObjectiveStudentRow(
                assessment_id=int(
                    row.assessment_id
                ),

                assessment_group_id=int(
                    row.assessment_group_id
                ),

                assessment_title=(
                        row.assessment_title
                        or f"Assessment #{row.assessment_id}"
                ),

                subject_name=(
                        row.subject_name
                        or "—"
                ),

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

                assessment_objective_id=int(
                    row.assessment_objective_id
                ),

                learning_objective_id=int(
                    row.learning_objective_id
                ),

                objective_code=(
                        row.objective_code
                        or "—"
                ),

                objective_title=(
                        row.objective_title
                        or "—"
                ),

                objective_max_score=(
                    row.objective_max_score
                ),

                assessment_student_id=int(
                    row.assessment_student_id
                ),

                student_id=int(
                    row.student_id
                ),

                student_name=(
                        row.student_name
                        or f"ID {row.student_id}"
                ),

                participation_status=(
                    row.participation_status
                ),

                score=row.score,

                max_score=(
                    row.result_max_score
                ),

                percent=row.percent,
            )
            for row in rows
        ]
