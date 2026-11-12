# app/modules/assessment/repositories/assessment_student_repo.py

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.models import (
    Assessment,
    AssessmentGroup,
    AssessmentStudent,
)


class AssessmentStudentRepo:
    """
    Репозиторий участников Assessment.

    Отвечает только за AssessmentStudent:

        - создание участников;
        - получение участника;
        - проверку принадлежности Assessment;
        - school boundary;
        - teacher group boundary.

    Здесь нет:
        - бизнес-логики;
        - расчёта результатов;
        - проверки статусов Assessment;
        - commit.

    commit выполняет Service Layer.
    """

    # =========================================================
    # CREATE
    # =========================================================

    @staticmethod
    async def add_many(
        db: AsyncSession,
        *,
        students: Sequence[AssessmentStudent],
    ) -> list[AssessmentStudent]:
        """
        Добавить участников Assessment одним batch-вызовом.
        """

        items = list(students)

        if not items:
            return []

        db.add_all(items)

        await db.flush()

        return items

    # =========================================================
    # GET BY ID
    # =========================================================

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        *,
        assessment_student_id: int,
    ) -> AssessmentStudent | None:
        """
        Получить AssessmentStudent по первичному ключу.

        Метод не выполняет school / assessment boundary.
        Для пользовательских операций предпочтительно
        использовать get_for_assessment().
        """

        stmt = (
            select(AssessmentStudent)
            .where(
                AssessmentStudent.id
                == assessment_student_id,
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    # =========================================================
    # ASSESSMENT BOUNDARY
    # =========================================================

    @staticmethod
    async def get_for_assessment(
        db: AsyncSession,
        *,
        assessment_student_id: int,
        assessment_id: int,
        school_id: int,
    ) -> AssessmentStudent | None:
        """
        Получить участника конкретного Assessment
        внутри конкретной школы.

        Security boundary:

            AssessmentStudent
                -> AssessmentGroup
                -> Assessment

        Проверяются одновременно:

            assessment_student_id
            assessment_id
            school_id
        """

        stmt = (
            select(AssessmentStudent)
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
            .where(
                AssessmentStudent.id
                == assessment_student_id,

                AssessmentGroup.assessment_id
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
    # ONLINE ACCESS
    # =========================================================

    @staticmethod
    async def get_by_access_token_hash(
        db: AsyncSession,
        *,
        access_token_hash: str,
    ) -> AssessmentStudent | None:
        """
        Получить участника по хэшу персонального
        токена online-доступа.

        В БД хранится только хэш токена.

        Метод намеренно не проверяет бизнес-состояние:
            - Assessment.input_mode;
            - Assessment.status;
            - participation_status;
            - время проведения.

        Эти правила относятся к Service Layer.
        """

        stmt = (
            select(AssessmentStudent)
            .where(
                AssessmentStudent.access_token_hash
                == access_token_hash,
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_online_access_context(
        db: AsyncSession,
        *,
        access_token_hash: str,
    ) -> tuple[
        AssessmentStudent,
        AssessmentGroup,
        Assessment,
    ] | None:
        """
        Получить полный контекст online-доступа ученика:

            AssessmentStudent
                -> AssessmentGroup
                -> Assessment

        Используется AssessmentExecutionService,
        чтобы одним SQL-запросом получить всё,
        что необходимо для проверки допуска.

        Repository не принимает решение,
        разрешено ли ученику начинать/продолжать работу.
        """

        stmt = (
            select(
                AssessmentStudent,
                AssessmentGroup,
                Assessment,
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
            .where(
                AssessmentStudent.access_token_hash
                == access_token_hash,

                AssessmentStudent.school_id
                == AssessmentGroup.school_id,

                AssessmentGroup.school_id
                == Assessment.school_id,
            )
        )

        result = await db.execute(stmt)

        row = result.one_or_none()

        if row is None:
            return None

        return (
            row.AssessmentStudent,
            row.AssessmentGroup,
            row.Assessment,
        )

    @staticmethod
    async def set_access_token_hash(
        db: AsyncSession,
        *,
        assessment_student: AssessmentStudent,
        access_token_hash: str,
    ) -> AssessmentStudent:
        """
        Назначить участнику хэш персонального
        online access token.

        Сам открытый токен сюда не передаётся
        для хранения.

        commit выполняет Service Layer.
        """

        assessment_student.access_token_hash = (
            access_token_hash
        )

        await db.flush()

        return assessment_student

    @staticmethod
    async def clear_access_token(
        db: AsyncSession,
        *,
        assessment_student: AssessmentStudent,
    ) -> AssessmentStudent:
        """
        Отозвать online-доступ участника.

        После очистки старый токен больше
        не может быть найден через repository.
        """

        assessment_student.access_token_hash = None

        await db.flush()

        return assessment_student

    # =========================================================
    # ASSESSMENT PARTICIPANTS
    # =========================================================

    @staticmethod
    async def get_many_for_assessment(
        db: AsyncSession,
        *,
        assessment_id: int,
        school_id: int,
    ) -> list[AssessmentStudent]:
        """
        Получить всех участников Assessment
        внутри указанной школы.

        Используется, например:
            - при ручном сохранении результатов;
            - при batch-операциях Assessment;
            - в будущем online execution.

        Один SQL-запрос.
        """

        stmt = (
            select(AssessmentStudent)
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
            .where(
                AssessmentGroup.assessment_id
                == assessment_id,

                AssessmentStudent.school_id
                == school_id,

                AssessmentGroup.school_id
                == school_id,

                Assessment.school_id
                == school_id,
            )
            .order_by(
                AssessmentGroup.id.asc(),
                AssessmentStudent.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    # =========================================================
    # TEACHER BOUNDARY
    # =========================================================

    @staticmethod
    async def get_many_for_teacher_assessment(
        db: AsyncSession,
        *,
        assessment_id: int,
        school_id: int,
        teacher_staff_member_id: int,
    ) -> list[AssessmentStudent]:
        """
        Получить участников только тех AssessmentGroup,
        которые закреплены за текущим учителем.

        Security boundary:

            assessment_id
            school_id
            teacher_staff_member_id

        Один SQL-запрос.
        """

        stmt = (
            select(AssessmentStudent)
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
            .where(
                AssessmentGroup.assessment_id
                == assessment_id,

                AssessmentStudent.school_id
                == school_id,

                AssessmentGroup.school_id
                == school_id,

                Assessment.school_id
                == school_id,

                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,
            )
            .order_by(
                AssessmentGroup.id.asc(),
                AssessmentStudent.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )
