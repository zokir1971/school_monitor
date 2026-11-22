# app/modules/education/services/teaching_load_service.py

from __future__ import annotations

from app.modules.education.repositories.teacher_choices_repo import TeacherChoicesRepo, TeacherChoice
from app.modules.education.helpers.teacher_subject_choices import build_teacher_choices

from datetime import date
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.education.models import (
    SchoolClass,
    SchoolClassSubjectTeacher,
    Subject,
)
from app.modules.education.repositories.class_subject_teacher_repo import (
    SchoolClassSubjectTeacherRepo,
)
from app.modules.education.repositories.curriculum_repo import CurriculumRepo
from app.modules.education.repositories.school_class_repo import (
    SchoolClassRepo,
)
from app.modules.education.repositories.subject_repo import (
    SubjectRepo,
)
from app.modules.education.schemas.teaching_load import (
    TeachingLoadAssignmentDTO,
    TeachingLoadClassDTO,
    TeachingLoadCreateDTO,
    TeachingLoadPageDTO,
    TeachingLoadSubjectDTO,
    TeachingLoadTeacherDTO,
)
from app.modules.staff.models_staff_school import SchoolStaffMember


class TeachingLoadError(ValueError):
    """
    Ошибка бизнес-логики управления учебной нагрузкой.
    """


class TeachingLoadService:
    """
    Управление учебной нагрузкой школы.

    Связь:

        школа
        + класс
        + предмет
        + преподаватель

    Service Layer отвечает за:
        - границы школы;
        - активность класса, предмета и сотрудника;
        - защиту от дублирования;
        - смену основного преподавателя;
        - сохранение истории назначений;
        - транзакцию.
    """

    # =========================================================
    # PAGE
    # =========================================================

    @classmethod
    async def get_page(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            academic_year_start: int,
    ) -> TeachingLoadPageDTO:
        """
        Подготовить страницу управления
        учебной нагрузкой школы.
        """

        cls._validate_school_id(school_id)
        cls._validate_academic_year_start(
            academic_year_start
        )

        # =========================================================
        # DATA
        # =========================================================

        assignments = (
            await SchoolClassSubjectTeacherRepo
            .list_active_for_school_year(
                db,
                school_id=school_id,
                academic_year_start=academic_year_start,
            )
        )

        classes = (
            await SchoolClassRepo
            .get_active_by_school_and_year(
                db,
                school_id=school_id,
                academic_year_start=academic_year_start,
            )
        )

        subjects = await SubjectRepo.get_active_all(
            db
        )

        teachers = await cls._list_active_teachers(
            db,
            school_id=school_id,
        )

        # =========================================================
        # LOOKUP MAPS
        # =========================================================

        class_map = {
            cast(int, item.id): item
            for item in classes
        }

        subject_map = {
            cast(int, item.id): item
            for item in subjects
        }

        teacher_map = {
            cast(int, item.id): item
            for item in teachers
        }

        # =========================================================
        # ASSIGNMENTS DTO
        # =========================================================

        assignment_dtos: list[
            TeachingLoadAssignmentDTO
        ] = []

        for assignment in assignments:
            assignment_id = cast(
                int,
                assignment.id,
            )

            school_class_id = cast(
                int,
                assignment.school_class_id,
            )

            subject_id = cast(
                int,
                assignment.subject_id,
            )

            staff_member_id = cast(
                int | None,
                assignment.staff_member_id,
            )

            is_primary = cast(
                bool,
                assignment.is_primary,
            )

            school_class = class_map.get(
                school_class_id
            )

            subject = subject_map.get(
                subject_id
            )

            teacher = (
                teacher_map.get(staff_member_id)
                if staff_member_id is not None
                else None
            )

            assignment_dtos.append(
                TeachingLoadAssignmentDTO(
                    id=assignment_id,

                    school_class_id=school_class_id,
                    class_name=cls._class_name(
                        school_class
                    ),

                    subject_id=subject_id,
                    subject_name=cls._subject_name(
                        subject
                    ),

                    staff_member_id=staff_member_id,
                    teacher_name=cls._teacher_name(
                        assignment=assignment,
                        teacher=teacher,
                    ),

                    is_primary=is_primary,
                )
            )

        # =========================================================
        # PAGE DTO
        # =========================================================

        return TeachingLoadPageDTO(
            academic_year_start=academic_year_start,
            academic_year_label=(
                f"{academic_year_start}/"
                f"{academic_year_start + 1}"
            ),

            assignments=assignment_dtos,
            teacher_choices=build_teacher_choices(teachers, subjects, assignments),

            classes=[
                TeachingLoadClassDTO(
                    id=cast(int, item.id),
                    name=cls._class_name(item),
                )
                for item in classes
            ],

            subjects=[
                TeachingLoadSubjectDTO(
                    id=cast(int, item.id),
                    name=cls._subject_name(item),
                )
                for item in subjects
            ],

            teachers=[
                TeachingLoadTeacherDTO(
                    staff_member_id=cast(
                        int,
                        item.id,
                    ),
                    full_name=item.full_name,
                )
                for item in teachers
            ],
        )

    # =========================================================
    # CREATE
    # =========================================================

    @classmethod
    async def create_assignment(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            dto: TeachingLoadCreateDTO,
    ) -> SchoolClassSubjectTeacher:
        """
        Создать назначение учебной нагрузки.

        Если создаётся новое основное назначение,
        прежний основной преподаватель того же
        предмета и класса закрывается исторически.
        """

        cls._validate_school_id(school_id)
        cls._validate_create_dto(dto)

        try:
            # =====================================================
            # CLASS
            # =====================================================

            school_class = await cls._get_school_class(
                db,
                school_id=school_id,
                school_class_id=dto.school_class_id,
            )

            if not school_class.is_active:
                raise TeachingLoadError(
                    "Таңдалған сынып белсенді емес."
                )

            if school_class.instruction_language:
                offer = await CurriculumRepo.class_offer(
                    db, school_id, dto.school_class_id, dto.subject_id,
                )
                if offer is None:
                    raise TeachingLoadError("Предмет не входит в набор класса. Откройте раздел предметов класса.")
                if offer.split_enabled:
                    raise TeachingLoadError("Предмет разделён на подгруппы. Назначьте учителей в разделе предметов "
                                            "класса.")

            # =====================================================
            # SUBJECT
            # =====================================================

            await cls._get_active_subject(
                db,
                subject_id=dto.subject_id,
            )

            # =====================================================
            # TEACHER
            # =====================================================

            teacher = await cls._get_active_teacher(
                db,
                school_id=school_id,
                staff_member_id=dto.staff_member_id,
            )

            # =====================================================
            # DUPLICATE
            # =====================================================

            existing = (
                await SchoolClassSubjectTeacherRepo
                .get_active_assignment(
                    db,
                    school_id=school_id,
                    school_class_id=dto.school_class_id,
                    subject_id=dto.subject_id,
                    staff_member_id=dto.staff_member_id,
                )
            )

            if existing is not None:
                raise TeachingLoadError(
                    "Бұл мұғалімге осы сынып пен пән "
                    "бойынша белсенді жүктеме бұрыннан "
                    "тағайындалған."
                )

            now = date.today()

            # =====================================================
            # PRIMARY TEACHER
            # =====================================================

            if dto.is_primary:
                current_primary = (
                    await SchoolClassSubjectTeacherRepo
                    .get_active_primary_assignment(
                        db,
                        school_id=school_id,
                        school_class_id=dto.school_class_id,
                        subject_id=dto.subject_id,
                    )
                )

                if current_primary is not None:
                    SchoolClassSubjectTeacherRepo.deactivate(
                        current_primary,
                        unassigned_at=now,
                    )

            # =====================================================
            # CREATE ASSIGNMENT
            # =====================================================

            assignment = SchoolClassSubjectTeacher(
                school_id=school_id,
                school_class_id=dto.school_class_id,
                subject_id=dto.subject_id,
                staff_member_id=dto.staff_member_id,

                teacher_name_snapshot=teacher.full_name,

                is_primary=dto.is_primary,
                is_active=True,

                assigned_at=now,
                unassigned_at=None,
            )

            await SchoolClassSubjectTeacherRepo.add(
                db,
                assignment=assignment,
            )

            await SchoolClassSubjectTeacherRepo.flush(
                db
            )

            await db.commit()
            await SchoolClassSubjectTeacherRepo.refresh(db, assignment)

            return assignment

        except Exception:
            await db.rollback()
            raise
        
    # =========================================================
    # DEACTIVATE
    # =========================================================

    @classmethod
    async def deactivate_assignment(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
        assignment_id: int,
    ) -> None:
        """
        Снять назначение с учебной нагрузки.

        Физического DELETE нет:
        запись остаётся в истории.
        """

        cls._validate_school_id(school_id)

        if assignment_id <= 0:
            raise TeachingLoadError(
                "Жүктеме тағайындауы қате."
            )

        try:
            assignment = (
                await SchoolClassSubjectTeacherRepo
                .get_by_id_for_school(
                    db,
                    assignment_id=assignment_id,
                    school_id=school_id,
                )
            )

            if assignment is None:
                raise TeachingLoadError(
                    "Жүктеме тағайындауы табылмады."
                )

            if not assignment.is_active:
                raise TeachingLoadError(
                    "Бұл жүктеме бұрын тоқтатылған."
                )

            SchoolClassSubjectTeacherRepo.deactivate(
                assignment,
                unassigned_at=date.today(),
            )

            await SchoolClassSubjectTeacherRepo.flush(
                db
            )

            await db.commit()

        except Exception:
            await db.rollback()
            raise

    # =========================================================
    # CLASS
    # =========================================================

    @staticmethod
    async def _get_school_class(
        db: AsyncSession,
        *,
        school_id: int,
        school_class_id: int,
    ) -> SchoolClass:
        """
        Получить класс строго внутри школы.
        """

        school_class = (
            await SchoolClassRepo.get_by_id_for_school(
                db,
                class_id=school_class_id,
                school_id=school_id,
            )
        )

        if school_class is None:
            raise TeachingLoadError(
                "Сынып табылмады."
            )

        return school_class

    # =========================================================
    # SUBJECT
    # =========================================================

    @staticmethod
    async def _get_active_subject(
        db: AsyncSession,
        *,
        subject_id: int,
    ) -> Subject:
        """
        Получить активный предмет.
        """

        subject = await SubjectRepo.get_active_by_id(
            db,
            subject_id=subject_id,
        )

        if subject is None:
            raise TeachingLoadError(
                "Пән табылмады немесе белсенді емес."
            )

        return subject

    # =========================================================
    # TEACHER
    # =========================================================

    @staticmethod
    async def _get_active_teacher(
        db: AsyncSession,
        *,
        school_id: int,
        staff_member_id: int,
    ) -> TeacherChoice:
        """
        Получить активного сотрудника
        строго внутри школы.
        """

        teacher = await TeacherChoicesRepo.get_active(
            db, school_id=school_id, staff_member_id=staff_member_id,
        )

        if teacher is None:
            raise TeachingLoadError(
                "Мұғалім табылмады немесе "
                "белсенді емес."
            )

        return teacher

    @staticmethod
    async def _list_active_teachers(
        db: AsyncSession,
        *,
        school_id: int,
    ) -> list[TeacherChoice]:
        """
        Активные сотрудники школы, которым
        потенциально можно назначить нагрузку.
        """

        members = await TeacherChoicesRepo.list_active(db, school_id=school_id)

        return list(members)

    # =========================================================
    # DISPLAY
    # =========================================================

    @staticmethod
    def _class_name(
        school_class: SchoolClass | None,
    ) -> str:
        if school_class is None:
            return "—"

        letter = (
            school_class.letter or ""
        ).strip()

        if letter:
            return (
                f"{school_class.grade_level}"
                f"{letter}"
            )

        return str(
            school_class.grade_level
        )

    @staticmethod
    def _subject_name(
        subject: Subject | None,
    ) -> str:
        if subject is None:
            return "—"

        return (
            subject.name_kz
            or subject.code
            or str(subject.id)
        )

    @staticmethod
    def _teacher_name(
        *,
        assignment: SchoolClassSubjectTeacher,
        teacher: SchoolStaffMember | TeacherChoice | None,
    ) -> str:
        """
        Для активного сотрудника берём актуальное ФИО.

        Если сотрудник уже отсутствует,
        используем snapshot назначения.
        """

        if teacher is not None:
            return teacher.full_name

        return (
            assignment.teacher_name_snapshot
            or "—"
        )

    # =========================================================
    # VALIDATION
    # =========================================================

    @staticmethod
    def _validate_school_id(
        school_id: int,
    ) -> None:
        if school_id <= 0:
            raise TeachingLoadError(
                "Мектеп анықталмады."
            )

    @staticmethod
    def _validate_academic_year_start(
        academic_year_start: int,
    ) -> None:
        if academic_year_start < 2000:
            raise TeachingLoadError(
                "Оқу жылы қате көрсетілген."
            )

    @staticmethod
    def _validate_create_dto(
        dto: TeachingLoadCreateDTO,
    ) -> None:
        if dto.school_class_id <= 0:
            raise TeachingLoadError(
                "Сынып таңдалмаған."
            )

        if dto.subject_id <= 0:
            raise TeachingLoadError(
                "Пән таңдалмаған."
            )

        if dto.staff_member_id <= 0:
            raise TeachingLoadError(
                "Мұғалім таңдалмаған."
            )
