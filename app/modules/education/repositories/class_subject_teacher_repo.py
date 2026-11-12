# app/modules/education/repositories/class_subject_teacher_repo.py

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.education.models import (
    SchoolClassSubjectTeacher,
)


class SchoolClassSubjectTeacherRepo:
    """
    Репозиторий назначений преподавателей
    по связке:

        школа
        + класс
        + предмет
        + преподаватель

    Repository:
        - выполняет только SQL/ORM операции;
        - не содержит бизнес-логику;
        - не выполняет commit.

    Используется:
        - Assessment;
        - Question Bank / Human Review;
        - управлением учебной нагрузкой;
        - в будущем модулем расписания.
    """

    # =====================================================
    # ACTIVE PRIMARY TEACHERS
    # =====================================================

    @staticmethod
    async def get_active_primary_for_classes(
        db: AsyncSession,
        *,
        school_id: int,
        subject_id: int,
        school_class_ids: Sequence[int],
    ) -> list[SchoolClassSubjectTeacher]:
        """
        Получить активных основных преподавателей
        выбранного предмета сразу для нескольких классов.

        Выполняется одним SQL-запросом.

        Используется при создании Assessment,
        чтобы не создавать N+1.
        """

        class_ids = tuple(
            dict.fromkeys(
                school_class_ids
            )
        )

        if not class_ids:
            return []

        stmt = (
            select(
                SchoolClassSubjectTeacher
            )
            .where(
                SchoolClassSubjectTeacher.subgroup_id.is_(None),
                SchoolClassSubjectTeacher.school_id
                == school_id,

                SchoolClassSubjectTeacher.subject_id
                == subject_id,

                SchoolClassSubjectTeacher.school_class_id.in_(
                    class_ids
                ),

                SchoolClassSubjectTeacher.is_active
                .is_(True),

                SchoolClassSubjectTeacher.is_primary
                .is_(True),
            )
            .order_by(
                SchoolClassSubjectTeacher.school_class_id.asc(),
                SchoolClassSubjectTeacher.id.asc(),
            )
        )

        result = await db.execute(
            stmt
        )

        return list(
            result.scalars().all()
        )

    # =====================================================
    # ACTIVE PRIMARY ASSIGNMENTS FOR TEACHER
    # =====================================================

    @staticmethod
    async def get_active_primary_for_teacher(
        db: AsyncSession,
        *,
        school_id: int,
        staff_member_id: int,
    ) -> list[SchoolClassSubjectTeacher]:
        """
        Получить все активные основные назначения
        конкретного учителя внутри школы.

        Используется teacher create Assessment flow.
        """

        stmt = (
            select(
                SchoolClassSubjectTeacher
            )
            .where(
                SchoolClassSubjectTeacher.school_id
                == school_id,

                SchoolClassSubjectTeacher.staff_member_id
                == staff_member_id,

                SchoolClassSubjectTeacher.is_active
                .is_(True),

                SchoolClassSubjectTeacher.is_primary
                .is_(True),
            )
            .order_by(
                SchoolClassSubjectTeacher.subject_id.asc(),
                SchoolClassSubjectTeacher.school_class_id.asc(),
            )
        )

        result = await db.execute(
            stmt
        )

        return list(
            result.scalars().all()
        )

    # =====================================================
    # ALL ACTIVE ASSIGNMENTS FOR TEACHER
    # =====================================================

    @staticmethod
    async def get_active_for_teacher(
        db: AsyncSession,
        *,
        school_id: int,
        staff_member_id: int,
    ) -> list[SchoolClassSubjectTeacher]:
        """
        Получить все активные назначения
        конкретного учителя внутри школы.

        Учитываются:
            - основные;
            - дополнительные назначения.

        Используется Assessment и teaching scope.
        """

        stmt = (
            select(
                SchoolClassSubjectTeacher
            )
            .where(
                SchoolClassSubjectTeacher.school_id
                == school_id,

                SchoolClassSubjectTeacher.staff_member_id
                == staff_member_id,

                SchoolClassSubjectTeacher.is_active
                .is_(True),
            )
            .order_by(
                SchoolClassSubjectTeacher.subject_id.asc(),
                SchoolClassSubjectTeacher.school_class_id.asc(),
                SchoolClassSubjectTeacher.id.asc(),
            )
        )

        result = await db.execute(
            stmt
        )

        return list(
            result.scalars().all()
        )

    # =====================================================
    # SCHOOL YEAR LOAD
    # =====================================================

    @staticmethod
    async def list_active_for_school_year(
            db: AsyncSession,
            *,
            school_id: int,
            academic_year_start: int,
    ) -> list[SchoolClassSubjectTeacher]:
        """
        Получить всю активную учебную нагрузку школы
        за выбранный учебный год.

        Учебный год определяется через SchoolClass.
        """

        from app.modules.education.models import SchoolClass

        stmt = (
            select(SchoolClassSubjectTeacher)
            .join(
                SchoolClass,
                SchoolClass.id
                == SchoolClassSubjectTeacher.school_class_id,
            )
            .where(
                SchoolClassSubjectTeacher.school_id
                == school_id,

                SchoolClassSubjectTeacher.is_active
                .is_(True),

                SchoolClass.school_id
                == school_id,

                SchoolClass.academic_year_start
                == academic_year_start,

                SchoolClass.is_active
                .is_(True),
            )
            .order_by(
                SchoolClassSubjectTeacher.school_class_id.asc(),
                SchoolClassSubjectTeacher.subject_id.asc(),
                SchoolClassSubjectTeacher.is_primary.desc(),
                SchoolClassSubjectTeacher.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )
    
    # =====================================================
    # GET ASSIGNMENT
    # =====================================================

    @staticmethod
    async def get_by_id_for_school(
        db: AsyncSession,
        *,
        assignment_id: int,
        school_id: int,
    ) -> SchoolClassSubjectTeacher | None:
        """
        Получить назначение по ID только внутри школы.

        Возвращает как активное, так и историческое
        назначение.
        """

        stmt = (
            select(
                SchoolClassSubjectTeacher
            )
            .where(
                SchoolClassSubjectTeacher.id
                == assignment_id,

                SchoolClassSubjectTeacher.school_id
                == school_id,
            )
        )

        result = await db.execute(
            stmt
        )

        return result.scalar_one_or_none()

    # =====================================================
    # FIND ACTIVE ASSIGNMENT
    # =====================================================

    @staticmethod
    async def get_active_assignment(
        db: AsyncSession,
        *,
        school_id: int,
        school_class_id: int,
        subject_id: int,
        staff_member_id: int,
    ) -> SchoolClassSubjectTeacher | None:
        """
        Найти конкретное активное назначение:

            школа
            + класс
            + предмет
            + преподаватель
        """

        stmt = (
            select(
                SchoolClassSubjectTeacher
            )
            .where(
                SchoolClassSubjectTeacher.subgroup_id.is_(None),
                SchoolClassSubjectTeacher.school_id
                == school_id,

                SchoolClassSubjectTeacher.school_class_id
                == school_class_id,

                SchoolClassSubjectTeacher.subject_id
                == subject_id,

                SchoolClassSubjectTeacher.staff_member_id
                == staff_member_id,

                SchoolClassSubjectTeacher.is_active
                .is_(True),
            )
        )

        result = await db.execute(
            stmt
        )

        return result.scalar_one_or_none()

    # =====================================================
    # ACTIVE PRIMARY ASSIGNMENT
    # =====================================================

    @staticmethod
    async def get_active_primary_assignment(
        db: AsyncSession,
        *,
        school_id: int,
        school_class_id: int,
        subject_id: int,
    ) -> SchoolClassSubjectTeacher | None:
        """
        Получить текущего основного преподавателя
        предмета в конкретном классе.

        Используется Service Layer при смене
        основного преподавателя.
        """

        stmt = (
            select(
                SchoolClassSubjectTeacher
            )
            .where(
                SchoolClassSubjectTeacher.subgroup_id.is_(None),
                SchoolClassSubjectTeacher.school_id
                == school_id,

                SchoolClassSubjectTeacher.school_class_id
                == school_class_id,

                SchoolClassSubjectTeacher.subject_id
                == subject_id,

                SchoolClassSubjectTeacher.is_active
                .is_(True),

                SchoolClassSubjectTeacher.is_primary
                .is_(True),
            )
        )

        result = await db.execute(
            stmt
        )

        return result.scalar_one_or_none()

    # =====================================================
    # ADD
    # =====================================================

    @staticmethod
    async def add(
        db: AsyncSession,
        *,
        assignment: SchoolClassSubjectTeacher,
    ) -> SchoolClassSubjectTeacher:
        """
        Добавить новое назначение в текущую транзакцию.

        Commit выполняет Service Layer.
        """

        db.add(assignment)

        return assignment

    # =====================================================
    # DEACTIVATE
    # =====================================================

    @staticmethod
    def deactivate(
        assignment: SchoolClassSubjectTeacher,
        *,
        unassigned_at: date,
    ) -> None:
        """
        Закрыть активное назначение.

        Запись физически не удаляется,
        поскольку является частью истории нагрузки.

        Commit выполняет Service Layer.
        """

        assignment.is_active = False
        assignment.unassigned_at = unassigned_at

    # =====================================================
    # FLUSH
    # =====================================================

    @staticmethod
    async def flush(
        db: AsyncSession,
    ) -> None:
        """
        Flush текущей транзакции без commit.
        """

        await db.flush()

    @staticmethod
    async def refresh(db: AsyncSession, assignment: SchoolClassSubjectTeacher) -> None:
        await db.refresh(assignment)
