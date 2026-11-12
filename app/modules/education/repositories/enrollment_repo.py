# app/modules/education/repositories/enrollment_repo.py

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.modules.education.models import (
    SchoolClass,
    SchoolStudent,
    SchoolStudentEnrollment,
)


class SchoolStudentEnrollmentRepo:
    """
    Репозиторий истории принадлежности учащихся к классам.
    """

    @staticmethod
    async def get_active_by_student(
            db: AsyncSession,
            *,
            student_id: int,
            school_id: int,
    ) -> SchoolStudentEnrollment | None:
        """
        Текущее активное зачисление ученика.
        """

        stmt = (
            select(SchoolStudentEnrollment)
            .where(
                SchoolStudentEnrollment.school_id == school_id,
                SchoolStudentEnrollment.student_id == student_id,
                SchoolStudentEnrollment.is_active.is_(True),
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_by_class(
            db: AsyncSession,
            *,
            school_id: int,
            school_class_id: int,
    ) -> list[SchoolStudentEnrollment]:
        """
        Текущий состав одного класса.

        Student загружается явно, потому что в модели
        используется lazy="raise".
        """

        stmt = (
            select(SchoolStudentEnrollment)
            .join(
                SchoolStudent,
                SchoolStudent.id
                == SchoolStudentEnrollment.student_id,
            )
            .where(
                SchoolStudentEnrollment.school_id == school_id,
                SchoolStudentEnrollment.school_class_id
                == school_class_id,
                SchoolStudentEnrollment.is_active.is_(True),
                SchoolStudent.is_active.is_(True),
            )
            .options(
                joinedload(
                    SchoolStudentEnrollment.student
                )
            )
            .order_by(
                SchoolStudent.last_name.asc(),
                SchoolStudent.first_name.asc(),
                SchoolStudent.middle_name.asc().nullsfirst(),
                SchoolStudent.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().unique().all()
        )

    @staticmethod
    async def get_active_by_classes(
            db: AsyncSession,
            *,
            school_id: int,
            school_class_ids: Sequence[int],
    ) -> list[SchoolStudentEnrollment]:
        """
        Получить текущий контингент сразу нескольких классов.

        Именно этот метод будет использовать
        ManualAssessmentService при создании Assessment.
        """

        class_ids = tuple(
            dict.fromkeys(school_class_ids)
        )

        if not class_ids:
            return []

        stmt = (
            select(SchoolStudentEnrollment)
            .join(
                SchoolStudent,
                SchoolStudent.id
                == SchoolStudentEnrollment.student_id,
            )
            .join(
                SchoolClass,
                SchoolClass.id
                == SchoolStudentEnrollment.school_class_id,
            )
            .where(
                SchoolStudentEnrollment.school_id == school_id,
                SchoolStudentEnrollment.school_class_id.in_(
                    class_ids
                ),
                SchoolStudentEnrollment.is_active.is_(True),
                SchoolStudent.is_active.is_(True),
                SchoolClass.school_id == school_id,
            )
            .options(
                joinedload(
                    SchoolStudentEnrollment.student
                ),
                joinedload(
                    SchoolStudentEnrollment.school_class
                ),
            )
            .order_by(
                SchoolClass.grade_level.asc(),
                SchoolClass.letter.asc(),
                SchoolStudent.last_name.asc(),
                SchoolStudent.first_name.asc(),
                SchoolStudent.middle_name.asc().nullsfirst(),
                SchoolStudent.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().unique().all()
        )

    @staticmethod
    async def get_student_history(
            db: AsyncSession,
            *,
            student_id: int,
            school_id: int,
    ) -> list[SchoolStudentEnrollment]:
        """
        История классов ученика по годам.
        """

        stmt = (
            select(SchoolStudentEnrollment)
            .join(
                SchoolClass,
                SchoolClass.id
                == SchoolStudentEnrollment.school_class_id,
            )
            .where(
                SchoolStudentEnrollment.school_id == school_id,
                SchoolStudentEnrollment.student_id == student_id,
            )
            .options(
                joinedload(
                    SchoolStudentEnrollment.school_class
                )
            )
            .order_by(
                SchoolClass.academic_year_start.asc(),
                SchoolStudentEnrollment.enrolled_at.asc(),
                SchoolStudentEnrollment.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().unique().all()
        )

    @staticmethod
    async def get_student_class_on_date(
            db: AsyncSession,
            *,
            student_id: int,
            school_id: int,
            target_date: date,
    ) -> SchoolStudentEnrollment | None:
        """
        Найти класс ученика на конкретную дату.

        Это пригодится для исторической аналитики.
        """

        stmt = (
            select(SchoolStudentEnrollment)
            .where(
                SchoolStudentEnrollment.school_id == school_id,
                SchoolStudentEnrollment.student_id == student_id,
                SchoolStudentEnrollment.enrolled_at <= target_date,
                (
                        SchoolStudentEnrollment.left_at.is_(None)
                        | (
                                SchoolStudentEnrollment.left_at
                                >= target_date
                        )
                ),
            )
            .options(
                joinedload(
                    SchoolStudentEnrollment.school_class
                )
            )
            .order_by(
                SchoolStudentEnrollment.enrolled_at.desc(),
                SchoolStudentEnrollment.id.desc(),
            )
            .limit(1)
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_active_by_school(db: AsyncSession, *, school_id: int) -> list[SchoolStudentEnrollment]:
        result = await db.execute(
            select(SchoolStudentEnrollment).where(
                SchoolStudentEnrollment.school_id == school_id,
                SchoolStudentEnrollment.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    def add_many(db: AsyncSession, enrollments: Sequence[SchoolStudentEnrollment]) -> None:
        db.add_all(list(enrollments))

    @staticmethod
    async def flush(db: AsyncSession) -> None:
        await db.flush()
