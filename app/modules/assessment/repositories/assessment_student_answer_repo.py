# app/modules/assessment/repositories/assessment_student_answer_repo.py

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.enums import (
    AssessmentAnswerStatus,
)
from app.modules.assessment.models import (
    Assessment,
    AssessmentGroup,
    AssessmentQuestion,
    AssessmentStudent,
    AssessmentStudentAnswer,
)


class AssessmentStudentAnswerRepo:
    """
    Репозиторий ответов ученика на задания Assessment.

    Ответственность:
        - получение ответов;
        - проверка принадлежности ответа участнику;
        - Assessment / school boundary;
        - upsert ответа для autosave.

    Здесь нет:
        - проверки access token;
        - проверки статусов Assessment;
        - проверки времени выполнения;
        - автоматического оценивания;
        - определения правильности ответа;
        - commit.

    Всё перечисленное относится к Service Layer.
    """

    # =========================================================
    # GET
    # =========================================================

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        *,
        answer_id: int,
    ) -> AssessmentStudentAnswer | None:
        stmt = (
            select(AssessmentStudentAnswer)
            .where(
                AssessmentStudentAnswer.id
                == answer_id,
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_for_student_question(
        db: AsyncSession,
        *,
        assessment_student_id: int,
        question_id: int,
    ) -> AssessmentStudentAnswer | None:
        """
        Ответ конкретного участника
        на конкретный вопрос.
        """

        stmt = (
            select(AssessmentStudentAnswer)
            .where(
                AssessmentStudentAnswer.assessment_student_id
                == assessment_student_id,

                AssessmentStudentAnswer.question_id
                == question_id,
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_many_for_student(
        db: AsyncSession,
        *,
        assessment_student_id: int,
    ) -> list[AssessmentStudentAnswer]:
        """
        Все сохранённые ответы участника.
        """

        stmt = (
            select(AssessmentStudentAnswer)
            .join(
                AssessmentQuestion,
                AssessmentQuestion.id
                == AssessmentStudentAnswer.question_id,
            )
            .where(
                AssessmentStudentAnswer.assessment_student_id
                == assessment_student_id,
            )
            .order_by(
                AssessmentQuestion.order_no.asc(),
                AssessmentQuestion.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    # =========================================================
    # EXECUTION BOUNDARY
    # =========================================================

    @staticmethod
    async def get_for_execution(
        db: AsyncSession,
        *,
        assessment_student_id: int,
        question_id: int,
        assessment_id: int,
        school_id: int,
    ) -> AssessmentStudentAnswer | None:
        """
        Получить существующий ответ с полной
        проверкой execution boundary:

            AssessmentStudentAnswer
                -> AssessmentStudent
                -> AssessmentGroup
                -> Assessment

            AssessmentStudentAnswer
                -> AssessmentQuestion
                -> Assessment

        Таким образом нельзя получить ответ:
            - другого ученика;
            - другой работы;
            - другой школы;
            - на вопрос другого Assessment.
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
                AssessmentQuestion.id
                == AssessmentStudentAnswer.question_id,
            )
            .where(
                AssessmentStudentAnswer.assessment_student_id
                == assessment_student_id,

                AssessmentStudentAnswer.question_id
                == question_id,

                AssessmentGroup.assessment_id
                == assessment_id,

                AssessmentQuestion.assessment_id
                == assessment_id,

                AssessmentStudent.school_id
                == school_id,

                AssessmentGroup.school_id
                == school_id,

                Assessment.school_id
                == school_id,
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    # =========================================================
    # UPSERT
    # =========================================================

    @staticmethod
    async def upsert(
        db: AsyncSession,
        *,
        assessment_student_id: int,
        question_id: int,
        answer_data: dict[str, Any],
        max_score: Decimal,
        status: AssessmentAnswerStatus,
        score: Decimal | None = None,
        is_correct: bool | None = None,
    ) -> AssessmentStudentAnswer:
        """
        Создать или обновить ответ ученика.

        Unique boundary:
            assessment_student_id + question_id

        Используется для autosave и последующего grading.

        Метод намеренно принимает status явно:
        Repository не решает, считается ли ответ:
            NOT_ANSWERED,
            PENDING_REVIEW,
            CHECKED.

        commit выполняет Service Layer.
        """

        stmt = (
            insert(AssessmentStudentAnswer)
            .values(
                assessment_student_id=(
                    assessment_student_id
                ),
                question_id=question_id,
                answer_data=answer_data,
                max_score=max_score,
                status=status,
                score=score,
                is_correct=is_correct,
            )
            .on_conflict_do_update(
                constraint=(
                    "uq_assessment_student_answer"
                ),
                set_={
                    "answer_data": answer_data,
                    "max_score": max_score,
                    "status": status,
                    "score": score,
                    "is_correct": is_correct,
                    "checked_by_user_id": None,
                    "checked_at": None,
                },
            )
            .returning(
                AssessmentStudentAnswer
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one()

    @staticmethod
    async def add_missing_for_questions(
        db: AsyncSession,
        *,
        assessment_student_id: int,
        questions: Sequence[AssessmentQuestion],
        existing_question_ids: set[int],
    ) -> list[AssessmentStudentAnswer]:
        """
        Создать отсутствующие строки ответов участника
        для активных вопросов Assessment.

        Используется перед grading.

        Важный инвариант после выполнения:

            каждый переданный AssessmentQuestion
            имеет AssessmentStudentAnswer
            для данного assessment_student_id.

        Уже существующие ответы не изменяются.

        SQL-профиль:
            - 0 SELECT;
            - 1 batch INSERT / flush для всех missing answers.

        commit выполняет Service Layer.
        """

        missing_answers = [
            AssessmentStudentAnswer(
                assessment_student_id=assessment_student_id,
                question_id=question.id,
                answer_data={},
                score=Decimal("0"),
                max_score=question.max_score,
                status=AssessmentAnswerStatus.CHECKED,
                is_correct=False,
                checked_by_user_id=None,
                checked_at=None,
            )
            for question in questions
            if question.id not in existing_question_ids
        ]

        if not missing_answers:
            return []

        db.add_all(missing_answers)

        await db.flush()

        return missing_answers

    # =========================================================
    # BATCH
    # =========================================================

    @staticmethod
    async def get_many_for_students(
        db: AsyncSession,
        *,
        assessment_student_ids: Sequence[int],
    ) -> list[AssessmentStudentAnswer]:
        """
        Batch-загрузка ответов нескольких участников.

        Нужна позже для:
            - submit;
            - grading;
            - teacher review.

        Один SQL-запрос, без N+1.
        """

        ids = tuple(
            dict.fromkeys(
                assessment_student_ids
            )
        )

        if not ids:
            return []

        stmt = (
            select(AssessmentStudentAnswer)
            .join(
                AssessmentQuestion,
                AssessmentQuestion.id
                == AssessmentStudentAnswer.question_id,
            )
            .where(
                AssessmentStudentAnswer.assessment_student_id.in_(
                    ids
                ),
            )
            .order_by(
                AssessmentStudentAnswer.assessment_student_id.asc(),
                AssessmentQuestion.order_no.asc(),
                AssessmentQuestion.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )
