# app/modules/assessment/repositories/assessment_repo.py

from __future__ import annotations
from app.modules.assessment.repositories.assessment_name_columns import title_column

from collections.abc import Sequence

from sqlalchemy import select, func, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.modules.assessment.enums import AssessmentParticipationStatus, AssessmentStatus, AssessmentCheckpoint
from app.modules.assessment.models import (
    Assessment,
    AssessmentGroup,
    AssessmentObjective,
    AssessmentStudent,
    LearningObjective, AssessmentResult, AssessmentCampaign,
)
from app.modules.org.models import School, District


class AssessmentRepo:
    """
    Репозиторий структуры Assessment.

    Здесь нет:
        - расчёта процентов;
        - расчёта оценок;
        - бизнес-валидации статусов;
        - commit.

    Repository только работает с ORM / SQL.
    """

    # =====================================================
    # ASSESSMENT
    # =====================================================

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        *,
        assessment_id: int,
    ) -> Assessment | None:
        stmt = (
            select(Assessment)
            .where(
                Assessment.id == assessment_id,
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id_for_school(
        db: AsyncSession,
        *,
        assessment_id: int,
        school_id: int,
    ) -> Assessment | None:
        """
        Получить Assessment только внутри указанной школы.
        """

        stmt = (
            select(Assessment)
            .where(
                Assessment.id == assessment_id,
                Assessment.school_id == school_id,
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_checkpoint_conflicting_class_ids(
            db: AsyncSession,
            *,
            school_id: int,
            subject_id: int,
            academic_year_start: int,
            checkpoint: AssessmentCheckpoint,
            school_class_ids: Sequence[int],
    ) -> set[int]:
        """
        Найти классы, для которых уже существует Assessment
        с такой же официальной контрольной точкой.

        Конфликт определяется по ключу:

            school
            + subject
            + academic year
            + class
            + checkpoint

        Проверка выполняется через AssessmentGroup,
        потому что один Assessment может включать
        несколько классов.

        Repository только возвращает конфликтующие
        school_class_id и не принимает бизнес-решение.
        """

        class_ids = tuple(
            dict.fromkeys(
                int(class_id)
                for class_id in school_class_ids
                if int(class_id) > 0
            )
        )

        if not class_ids:
            return set()

        # Serialize official checkpoint reservation with online finalization.
        from app.modules.org.models import School
        await db.execute(select(School.id).where(School.id==school_id).with_for_update())
        stmt = (
            select(
                AssessmentGroup.school_class_id
            )
            .join(
                Assessment,
                Assessment.id
                == AssessmentGroup.assessment_id,
            )
            .where(
                Assessment.school_id
                == school_id,

                Assessment.subject_id
                == subject_id,

                Assessment.checkpoint
                == checkpoint,
                # Unfinalized diagnostic previews do not reserve official points.
                (Assessment.diagnostic_subject_id.is_(None) | (Assessment.status == AssessmentStatus.COMPLETED)),

                AssessmentGroup.academic_year_start_snapshot
                == academic_year_start,

                AssessmentGroup.school_class_id.in_(
                    class_ids
                ),
            )
            .distinct()
        )

        result = await db.execute(
            stmt
        )

        return {
            int(class_id)
            for class_id in result.scalars().all()
        }

    @staticmethod
    async def get_campaign_by_id_for_school(
            db: AsyncSession,
            *,
            campaign_id: int,
            school_id: int,
    ) -> AssessmentCampaign | None:
        """
        Получить AssessmentCampaign
        только внутри указанной школы.

        Используется как service-level
        security boundary перед созданием Assessment.
        """

        stmt = (
            select(
                AssessmentCampaign
            )
            .where(
                AssessmentCampaign.id
                == campaign_id,

                AssessmentCampaign.school_id
                == school_id,
            )
        )

        result = await db.execute(
            stmt
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def create_campaign(
            db: AsyncSession,
            *,
            campaign: AssessmentCampaign,
    ) -> AssessmentCampaign:
        """
        Добавить AssessmentCampaign
        в текущую транзакцию.

        commit выполняет Service Layer.
        """

        db.add(
            campaign
        )

        await db.flush()

        return campaign

    @staticmethod
    async def get_campaigns_for_school(
            db: AsyncSession,
            *,
            school_id: int,
    ) -> list[AssessmentCampaign]:
        """
        Получить кампании Assessment
        текущей школы.

        Используется:
            - для страницы списка кампаний;
            - для выбора campaign при создании Assessment.
        """

        stmt = (
            select(
                AssessmentCampaign
            )
            .where(
                AssessmentCampaign.school_id
                == school_id,
            )
            .order_by(
                AssessmentCampaign.created_at.desc(),
                AssessmentCampaign.id.desc(),
            )
        )

        result = await db.execute(
            stmt
        )

        return list(
            result.scalars().all()
        )

    @staticmethod
    async def get_assessments_for_campaign(
            db: AsyncSession,
            *,
            campaign_id: int,
            school_id: int,
    ) -> list[Assessment]:
        """
        Получить все предметные Assessment
        конкретной кампании внутри школы.
        """

        stmt = (
            select(
                Assessment
            )
            .where(
                Assessment.campaign_id
                == campaign_id,

                Assessment.school_id
                == school_id,
            )
            .order_by(
                Assessment.subject_name_snapshot.asc(),
                Assessment.id.asc(),
            )
        )

        result = await db.execute(
            stmt
        )

        return list(
            result.scalars().all()
        )

    @staticmethod
    async def get_for_completion(
            db: AsyncSession, *, assessment_id: int, school_id: int,
    ) -> Assessment | None:
        """Only the graph used by validation and quality summaries.

        Keep the full manual-entry loader for pages that need its extra data.
        selectinload batches large rosters; no query is issued per participant.
        """
        stmt = (select(Assessment)
                .where(Assessment.id == assessment_id, Assessment.school_id == school_id)
                .options(selectinload(Assessment.groups)
                         .selectinload(AssessmentGroup.students)
                         .selectinload(AssessmentStudent.result))
                .execution_options(populate_existing=True))
        return (await db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def get_for_manual_entry(
            db: AsyncSession,
            *,
            assessment_id: int,
            school_id: int,
    ) -> Assessment | None:
        """
        Получить Assessment для страницы ручного ввода.

        populate_existing=True нужен, чтобы при повторном чтении
        в рамках той же Session обновлялись уже загруженные
        relationships, включая AssessmentStudent.result.
        """

        stmt = (
            select(Assessment)
            .where(
                Assessment.id == assessment_id,
                Assessment.school_id == school_id,
            )
            .options(
                selectinload(
                    Assessment.subject
                ),

                selectinload(
                    Assessment.groups
                ).selectinload(
                    AssessmentGroup.school_class
                ),

                selectinload(
                    Assessment.groups
                ).selectinload(
                    AssessmentGroup.students
                ).selectinload(
                    AssessmentStudent.student
                ),

                selectinload(
                    Assessment.groups
                ).selectinload(
                    AssessmentGroup.students
                ).selectinload(
                    AssessmentStudent.result
                ),

                selectinload(
                    Assessment.groups
                ).selectinload(
                    AssessmentGroup.students
                ).selectinload(
                    AssessmentStudent.result
                ).selectinload(
                    AssessmentResult.objective_results
                ),

                selectinload(
                    Assessment.objectives
                ).selectinload(
                    AssessmentObjective.learning_objective
                ),
            )
            .execution_options(
                populate_existing=True,
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_for_teacher_manual_entry(
            db: AsyncSession,
            *,
            assessment_id: int,
            school_id: int,
            teacher_staff_member_id: int,
    ) -> Assessment | None:
        """
        Получить Assessment для ручного ввода
        результатов текущим учителем.

        Возвращаются только AssessmentGroup,
        закреплённые за текущим teacher.

        Security boundary:
            assessment_id
            school_id
            teacher_staff_member_id
        """

        stmt = (
            select(
                Assessment
            )
            .where(
                Assessment.id
                == assessment_id,

                Assessment.school_id
                == school_id,

                Assessment.groups.any(
                    AssessmentGroup.teacher_staff_member_id
                    == teacher_staff_member_id
                ),
            )
            .options(
                # -------------------------------------------------
                # Ограничиваем relationship Assessment.groups
                # только группами текущего teacher.
                # -------------------------------------------------

                with_loader_criteria(
                    AssessmentGroup,
                    AssessmentGroup.teacher_staff_member_id
                    == teacher_staff_member_id,
                    include_aliases=True,
                ),

                # -------------------------------------------------
                # SUBJECT
                # -------------------------------------------------

                selectinload(
                    Assessment.subject
                ),

                # -------------------------------------------------
                # GROUP -> CLASS
                # -------------------------------------------------

                selectinload(
                    Assessment.groups
                ).selectinload(
                    AssessmentGroup.school_class
                ),

                # -------------------------------------------------
                # GROUP -> STUDENTS -> STUDENT
                # -------------------------------------------------

                selectinload(
                    Assessment.groups
                ).selectinload(
                    AssessmentGroup.students
                ).selectinload(
                    AssessmentStudent.student
                ),

                # -------------------------------------------------
                # GROUP -> STUDENTS -> RESULT
                # -------------------------------------------------

                selectinload(
                    Assessment.groups
                ).selectinload(
                    AssessmentGroup.students
                ).selectinload(
                    AssessmentStudent.result
                ),

                # -------------------------------------------------
                # RESULT -> OBJECTIVE RESULTS
                # -------------------------------------------------

                selectinload(
                    Assessment.groups
                ).selectinload(
                    AssessmentGroup.students
                ).selectinload(
                    AssessmentStudent.result
                ).selectinload(
                    AssessmentResult.objective_results
                ),

                # -------------------------------------------------
                # ASSESSMENT OBJECTIVES
                # -------------------------------------------------

                selectinload(
                    Assessment.objectives
                ).selectinload(
                    AssessmentObjective.learning_objective
                ),
            )
            .execution_options(
                populate_existing=True
            )
        )

        result = await db.execute(
            stmt
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        assessment: Assessment,
    ) -> Assessment:
        """
        Добавить Assessment в текущую транзакцию.

        commit выполняет Service Layer.
        """

        db.add(assessment)

        await db.flush()

        return assessment

    # =====================================================
    # GROUPS
    # =====================================================

    @staticmethod
    async def add_groups(
        db: AsyncSession,
        *,
        groups: Sequence[AssessmentGroup],
    ) -> list[AssessmentGroup]:
        """
        Добавить группы / классы Assessment.
        """

        items = list(groups)

        if not items:
            return []

        db.add_all(items)

        await db.flush()

        return items

    @staticmethod
    async def get_groups(
        db: AsyncSession,
        *,
        assessment_id: int,
    ) -> list[AssessmentGroup]:
        stmt = (
            select(AssessmentGroup)
            .where(
                AssessmentGroup.assessment_id
                == assessment_id,
            )
            .order_by(
                AssessmentGroup.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    # =====================================================
    # LEARNING OBJECTIVES
    # =====================================================

    @staticmethod
    async def get_learning_objectives(
        db: AsyncSession,
        *,
        subject_id: int,
        grade_level: int,
        quarter: int | None = None,
    ) -> list[LearningObjective]:
        """
        Активные учебные цели предмета и класса.
        """

        stmt = (
            select(LearningObjective)
            .where(
                LearningObjective.subject_id
                == subject_id,
                LearningObjective.grade_level
                == grade_level,
                LearningObjective.is_active.is_(True),
            )
            .order_by(
                LearningObjective.code.asc(),
                LearningObjective.id.asc(),
            )
        )

        if quarter is not None:
            stmt=stmt.where(LearningObjective.quarter==quarter)

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    @staticmethod
    async def get_learning_objectives_by_ids(
        db: AsyncSession,
        *,
        learning_objective_ids: Sequence[int],
        subject_id: int,
    ) -> list[LearningObjective]:
        """
        Получить выбранные цели и одновременно проверить,
        что они относятся к выбранному предмету.
        """

        ids = tuple(
            dict.fromkeys(
                learning_objective_ids
            )
        )

        if not ids:
            return []

        stmt = (
            select(LearningObjective)
            .where(
                LearningObjective.id.in_(ids),
                LearningObjective.subject_id
                == subject_id,
                LearningObjective.is_active.is_(True),
            )
            .order_by(
                LearningObjective.code.asc(),
                LearningObjective.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    # =====================================================
    # ASSESSMENT OBJECTIVES
    # =====================================================

    @staticmethod
    async def add_objectives(
        db: AsyncSession,
        *,
        objectives: Sequence[
            AssessmentObjective
        ],
    ) -> list[AssessmentObjective]:
        items = list(objectives)

        if not items:
            return []

        db.add_all(items)

        await db.flush()

        return items

    # =====================================================
    # ASSESSMENT LIST
    # =====================================================

    @staticmethod
    def _build_list_participant_stats_subquery(
            *,
            school_id: int,
            teacher_staff_member_id: int | None = None,
            assessment_ids=None,
    ):
        """
        Агрегированная статистика участников Assessment.

        Если teacher_staff_member_id не указан:
            считаются все группы Assessment школы.

        Если teacher_staff_member_id указан:
            считаются только группы текущего учителя.

        Подзапрос отделён от основного list query,
        чтобы joins с AssessmentGroup metadata
        не размножали строки учеников и результатов.
        """

        stmt = (
            select(
                AssessmentGroup.assessment_id.label(
                    "assessment_id"
                ),

                func.count(
                    AssessmentStudent.id
                ).label(
                    "total_students"
                ),

                func.count(
                    AssessmentStudent.id
                )
                .filter(
                    AssessmentStudent.participation_status
                    == AssessmentParticipationStatus.COMPLETED
                )
                .label(
                    "completed_students"
                ),

                func.count(
                    AssessmentStudent.id
                )
                .filter(
                    AssessmentStudent.participation_status
                    == AssessmentParticipationStatus.ABSENT
                )
                .label(
                    "absent_students"
                ),

                func.count(
                    AssessmentStudent.id
                )
                .filter(
                    AssessmentStudent.participation_status.in_(
                        (
                            AssessmentParticipationStatus.COMPLETED,
                            AssessmentParticipationStatus.ABSENT,
                            AssessmentParticipationStatus.EXCUSED,
                            AssessmentParticipationStatus.NOT_COMPLETED,
                        )
                    )
                )
                .label(
                    "processed_students"
                ),

                func.count(
                    AssessmentResult.id
                )
                .label(
                    "result_count"
                ),
            )
            .select_from(
                AssessmentGroup
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
            .where(
                AssessmentGroup.school_id
                == school_id,
            )
        )

        if assessment_ids is not None:
            stmt = stmt.where(AssessmentGroup.assessment_id.in_(assessment_ids))

        if teacher_staff_member_id is not None:
            stmt = stmt.where(
                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,
            )

        return (
            stmt
            .group_by(
                AssessmentGroup.assessment_id,
            )
            .subquery(
                "assessment_list_participant_stats"
            )
        )

    @staticmethod
    def _build_list_group_metadata_subquery(
            *,
            school_id: int,
            teacher_staff_member_id: int | None = None,
            assessment_ids=None,
    ):
        """
        Агрегированные snapshot-данные групп Assessment.

        School list:
            все группы Assessment.

        Teacher list:
            только группы текущего учителя.

        array_agg(DISTINCT ...) используется намеренно:
            один Assessment может содержать несколько групп
            с одинаковым teacher snapshot.
        """

        stmt = (
            select(
                AssessmentGroup.assessment_id.label(
                    "assessment_id"
                ),

                func.array_agg(
                    func.distinct(
                        AssessmentGroup.class_name_snapshot
                    )
                ).label(
                    "class_names"
                ),

                func.array_agg(
                    func.distinct(
                        AssessmentGroup.teacher_name_snapshot
                    )
                )
                .filter(
                    AssessmentGroup.teacher_name_snapshot
                    .is_not(None)
                )
                .label(
                    "teacher_names"
                ),
            )
            .where(
                AssessmentGroup.school_id
                == school_id,
            )
        )

        if assessment_ids is not None:
            stmt = stmt.where(AssessmentGroup.assessment_id.in_(assessment_ids))

        if teacher_staff_member_id is not None:
            stmt = stmt.where(
                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,
            )

        return (
            stmt
            .group_by(
                AssessmentGroup.assessment_id,
            )
            .subquery(
                "assessment_list_group_metadata"
            )
        )

    @staticmethod
    def _apply_list_filters(
            stmt,
            *,
            school_id: int,
            academic_year_start: int | None,
            subject_id: int | None,
            grade_level: int | None,
            status: AssessmentStatus | None,
            teacher_staff_member_id: int | None = None,
    ):
        """
        Применить фильтры списка Assessment.

        Важно:
            academic_year и grade фильтруются через EXISTS.

        Благодаря этому фильтр определяет,
        должен ли Assessment попасть в список,
        но не обрезает его агрегированную статистику.

        Для teacher list EXISTS дополнительно ограничен
        группами текущего учителя.
        """

        if subject_id is not None:
            stmt = stmt.where(
                Assessment.subject_id
                == subject_id,
            )

        if status is not None:
            stmt = stmt.where(
                Assessment.status
                == status,
            )

        if (
                academic_year_start is not None
                or grade_level is not None
                or teacher_staff_member_id is not None
        ):
            group_conditions = [
                AssessmentGroup.assessment_id
                == Assessment.id,

                AssessmentGroup.school_id
                == school_id,
            ]

            if teacher_staff_member_id is not None:
                group_conditions.append(
                    AssessmentGroup.teacher_staff_member_id
                    == teacher_staff_member_id
                )

            if academic_year_start is not None:
                group_conditions.append(
                    AssessmentGroup.academic_year_start_snapshot
                    == academic_year_start
                )

            if grade_level is not None:
                group_conditions.append(
                    AssessmentGroup.grade_level_snapshot
                    == grade_level
                )

            stmt = stmt.where(
                exists(
                    select(1)
                    .select_from(
                        AssessmentGroup
                    )
                    .where(
                        *group_conditions
                    )
                )
            )

        return stmt

    @classmethod
    def _list_candidates(cls, *, school_id, academic_year_start, subject_id,
                         grade_level, status, teacher_staff_member_id=None):
        if all(value is None for value in (academic_year_start, subject_id, grade_level, status)):
            return None  # No narrower filter: retain the simple school-scoped query.
        stmt = cls._apply_list_filters(
            select(Assessment.id).where(Assessment.school_id == school_id),
            school_id=school_id, academic_year_start=academic_year_start,
            subject_id=subject_id, grade_level=grade_level, status=status,
            teacher_staff_member_id=teacher_staff_member_id)
        candidates = stmt.cte('assessment_list_candidates')
        return select(candidates.c.id)

    @classmethod
    async def get_school_list_rows(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            status: AssessmentStatus | None = None,
    ):
        """
        Список Assessment школы.

        Используется:
            - SCHOOL_ADMIN;
            - SCHOOL_STAFF.

        Возвращает по одному SQL row на Assessment.

        Статистика и metadata рассчитываются SQL,
        дополнительных запросов классов/учителей нет.
        """

        assessment_ids = cls._list_candidates(
            school_id=school_id, academic_year_start=academic_year_start,
            subject_id=subject_id, grade_level=grade_level, status=status,
            teacher_staff_member_id=None)

        participant_stats = (
            cls._build_list_participant_stats_subquery(
                assessment_ids=assessment_ids,
                school_id=school_id,
            )
        )

        group_metadata = (
            cls._build_list_group_metadata_subquery(
                assessment_ids=assessment_ids,
                school_id=school_id,
            )
        )

        stmt = (
            select(
                Assessment.id.label(
                    "assessment_id"
                ),

                title_column().label(
                    "title"
                ),

                Assessment.subject_id.label(
                    "subject_id"
                ),

                Assessment.subject_name_snapshot.label(
                    "subject_name"
                ),

                Assessment.assessment_type.label(
                    "assessment_type"
                ),

                Assessment.status.label(
                    "status"
                ),

                Assessment.input_mode.label(
                    "input_mode"
                ),

                Assessment.max_score.label(
                    "max_score"
                ),

                group_metadata.c.class_names.label(
                    "class_names"
                ),

                group_metadata.c.teacher_names.label(
                    "teacher_names"
                ),

                func.coalesce(
                    participant_stats.c.total_students,
                    0,
                ).label(
                    "total_students"
                ),

                func.coalesce(
                    participant_stats.c.completed_students,
                    0,
                ).label(
                    "completed_students"
                ),

                func.coalesce(
                    participant_stats.c.absent_students,
                    0,
                ).label(
                    "absent_students"
                ),

                func.coalesce(
                    participant_stats.c.processed_students,
                    0,
                ).label(
                    "processed_students"
                ),

                func.coalesce(
                    participant_stats.c.result_count,
                    0,
                ).label(
                    "result_count"
                ),
            )
            .select_from(
                Assessment
            )
            .outerjoin(
                participant_stats,
                participant_stats.c.assessment_id
                == Assessment.id,
            )
            .outerjoin(
                group_metadata,
                group_metadata.c.assessment_id
                == Assessment.id,
            )
            .where(
                Assessment.school_id
                == school_id,
            )
        )

        if assessment_ids is not None:
            stmt = stmt.where(Assessment.id.in_(assessment_ids))
        else:
            stmt = cls._apply_list_filters(
                stmt,
                school_id=school_id,
                academic_year_start=academic_year_start,
                subject_id=subject_id,
                grade_level=grade_level,
                status=status,
            )

        stmt = stmt.order_by(
            Assessment.created_at.desc(),
            Assessment.id.desc(),
        )

        result = await db.execute(
            stmt
        )

        return list(
            result.all()
        )

    @classmethod
    async def get_teacher_list_rows(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            academic_year_start: int | None = None,
            subject_id: int | None = None,
            grade_level: int | None = None,
            status: AssessmentStatus | None = None,
    ):
        """
        Список Assessment текущего учителя.

        Security boundary:
            school_id
            teacher_staff_member_id

        В строке отображаются и считаются
        только группы текущего учителя.

        Дополнительно возвращается:
            all_groups_belong_to_teacher

        Это позволяет Service Layer решить,
        может ли учитель завершить весь Assessment.
        """

        assessment_ids = cls._list_candidates(
            school_id=school_id, academic_year_start=academic_year_start,
            subject_id=subject_id, grade_level=grade_level, status=status,
            teacher_staff_member_id=teacher_staff_member_id)

        participant_stats = (
            cls._build_list_participant_stats_subquery(
                assessment_ids=assessment_ids,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
            )
        )

        group_metadata = (
            cls._build_list_group_metadata_subquery(
                assessment_ids=assessment_ids,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
            )
        )

        foreign_group_exists = (
            exists(
                select(1)
                .select_from(
                    AssessmentGroup
                )
                .where(
                    AssessmentGroup.assessment_id
                    == Assessment.id,

                    AssessmentGroup.school_id
                    == school_id,

                    AssessmentGroup.teacher_staff_member_id
                    .is_distinct_from(
                        teacher_staff_member_id
                    ),
                )
            )
        )

        stmt = (
            select(
                Assessment.id.label(
                    "assessment_id"
                ),

                title_column().label(
                    "title"
                ),

                Assessment.subject_id.label(
                    "subject_id"
                ),

                Assessment.subject_name_snapshot.label(
                    "subject_name"
                ),

                Assessment.assessment_type.label(
                    "assessment_type"
                ),

                Assessment.status.label(
                    "status"
                ),

                Assessment.input_mode.label(
                    "input_mode"
                ),

                Assessment.max_score.label(
                    "max_score"
                ),

                group_metadata.c.class_names.label(
                    "class_names"
                ),

                group_metadata.c.teacher_names.label(
                    "teacher_names"
                ),

                func.coalesce(
                    participant_stats.c.total_students,
                    0,
                ).label(
                    "total_students"
                ),

                func.coalesce(
                    participant_stats.c.completed_students,
                    0,
                ).label(
                    "completed_students"
                ),

                func.coalesce(
                    participant_stats.c.absent_students,
                    0,
                ).label(
                    "absent_students"
                ),

                func.coalesce(
                    participant_stats.c.processed_students,
                    0,
                ).label(
                    "processed_students"
                ),

                func.coalesce(
                    participant_stats.c.result_count,
                    0,
                ).label(
                    "result_count"
                ),

                (
                    ~foreign_group_exists
                ).label(
                    "all_groups_belong_to_teacher"
                ),
            )
            .select_from(
                Assessment
            )
            .join(
                group_metadata,
                group_metadata.c.assessment_id
                == Assessment.id,
            )
            .outerjoin(
                participant_stats,
                participant_stats.c.assessment_id
                == Assessment.id,
            )
            .where(
                Assessment.school_id
                == school_id,
            )
        )

        if assessment_ids is not None:
            stmt = stmt.where(Assessment.id.in_(assessment_ids))
        else:
            stmt = cls._apply_list_filters(
                stmt,
                school_id=school_id,
                academic_year_start=academic_year_start,
                subject_id=subject_id,
                grade_level=grade_level,
                status=status,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
            )

        stmt = stmt.order_by(
            Assessment.created_at.desc(),
            Assessment.id.desc(),
        )

        result = await db.execute(
            stmt
        )

        return list(
            result.all()
        )

    # =====================================================
    # LIST FILTER OPTIONS
    # =====================================================

    @staticmethod
    async def get_school_list_academic_years(
            db: AsyncSession,
            *,
            school_id: int,
    ) -> tuple[int, ...]:
        """
        Учебные годы, реально присутствующие
        в Assessment текущей школы.
        """

        stmt = (
            select(
                AssessmentGroup.academic_year_start_snapshot
            )
            .join(
                Assessment,
                Assessment.id
                == AssessmentGroup.assessment_id,
            )
            .where(
                Assessment.school_id
                == school_id,

                AssessmentGroup.school_id
                == school_id,
            )
            .distinct()
            .order_by(
                AssessmentGroup.academic_year_start_snapshot
                .desc()
            )
        )

        result = await db.execute(
            stmt
        )

        return tuple(
            int(value)
            for value in result.scalars().all()
        )

    @staticmethod
    async def get_teacher_list_academic_years(
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
    ) -> tuple[int, ...]:
        """
        Учебные годы Assessment текущего учителя.
        """

        stmt = (
            select(
                AssessmentGroup.academic_year_start_snapshot
            )
            .join(
                Assessment,
                Assessment.id
                == AssessmentGroup.assessment_id,
            )
            .where(
                Assessment.school_id
                == school_id,

                AssessmentGroup.school_id
                == school_id,

                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,
            )
            .distinct()
            .order_by(
                AssessmentGroup.academic_year_start_snapshot
                .desc()
            )
        )

        result = await db.execute(
            stmt
        )

        return tuple(
            int(value)
            for value in result.scalars().all()
        )

    @staticmethod
    async def get_school_list_subject_rows(
            db: AsyncSession,
            *,
            school_id: int,
    ):
        """
        Предметы, реально присутствующие
        в Assessment школы.

        Используется snapshot-название,
        чтобы исторический список не зависел
        от текущего состояния Subject.
        """

        stmt = (
            select(
                Assessment.subject_id.label(
                    "subject_id"
                ),

                Assessment.subject_name_snapshot.label(
                    "subject_name"
                ),
            )
            .where(
                Assessment.school_id
                == school_id,
            )
            .distinct()
            .order_by(
                Assessment.subject_name_snapshot.asc(),
                Assessment.subject_id.asc(),
            )
        )

        result = await db.execute(
            stmt
        )

        return list(
            result.all()
        )

    @staticmethod
    async def get_teacher_list_subject_rows(
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
    ):
        """
        Предметы, по которым у текущего учителя
        существуют Assessment.
        """

        stmt = (
            select(
                Assessment.subject_id.label(
                    "subject_id"
                ),

                Assessment.subject_name_snapshot.label(
                    "subject_name"
                ),
            )
            .join(
                AssessmentGroup,
                AssessmentGroup.assessment_id
                == Assessment.id,
            )
            .where(
                Assessment.school_id
                == school_id,

                AssessmentGroup.school_id
                == school_id,

                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,
            )
            .distinct()
            .order_by(
                Assessment.subject_name_snapshot.asc(),
                Assessment.subject_id.asc(),
            )
        )

        result = await db.execute(
            stmt
        )

        return list(
            result.all()
        )

    @staticmethod
    async def get_school_list_grade_levels(
            db: AsyncSession,
            *,
            school_id: int,
    ) -> tuple[int, ...]:
        """
        Параллели, реально присутствующие
        в Assessment школы.
        """

        stmt = (
            select(
                AssessmentGroup.grade_level_snapshot
            )
            .join(
                Assessment,
                Assessment.id
                == AssessmentGroup.assessment_id,
            )
            .where(
                Assessment.school_id
                == school_id,

                AssessmentGroup.school_id
                == school_id,
            )
            .distinct()
            .order_by(
                AssessmentGroup.grade_level_snapshot.asc()
            )
        )

        result = await db.execute(
            stmt
        )

        return tuple(
            int(value)
            for value in result.scalars().all()
        )

    @staticmethod
    async def get_teacher_list_grade_levels(
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
    ) -> tuple[int, ...]:
        """
        Параллели Assessment текущего учителя.
        """

        stmt = (
            select(
                AssessmentGroup.grade_level_snapshot
            )
            .join(
                Assessment,
                Assessment.id
                == AssessmentGroup.assessment_id,
            )
            .where(
                Assessment.school_id
                == school_id,

                AssessmentGroup.school_id
                == school_id,

                AssessmentGroup.teacher_staff_member_id
                == teacher_staff_member_id,
            )
            .distinct()
            .order_by(
                AssessmentGroup.grade_level_snapshot.asc()
            )
        )

        result = await db.execute(
            stmt
        )

        return tuple(
            int(value)
            for value in result.scalars().all()
        )

    # =====================================================
    # TEACHER ASSESSMENT OWNERSHIP
    # =====================================================

    @staticmethod
    async def teacher_owns_all_groups(
            db: AsyncSession,
            *,
            assessment_id: int,
            school_id: int,
            teacher_staff_member_id: int,
    ) -> bool:
        """
        Проверить, что ВСЕ группы Assessment
        принадлежат текущему учителю.

        Используется только как security boundary
        перед завершением Assessment учителем.

        Важно:
            наличие хотя бы одной своей группы недостаточно.
        """

        own_group_exists = (
            exists(
                select(1)
                .select_from(
                    AssessmentGroup
                )
                .where(
                    AssessmentGroup.assessment_id
                    == assessment_id,

                    AssessmentGroup.school_id
                    == school_id,

                    AssessmentGroup.teacher_staff_member_id
                    == teacher_staff_member_id,
                )
            )
        )

        foreign_group_exists = (
            exists(
                select(1)
                .select_from(
                    AssessmentGroup
                )
                .where(
                    AssessmentGroup.assessment_id
                    == assessment_id,

                    AssessmentGroup.school_id
                    == school_id,

                    AssessmentGroup.teacher_staff_member_id
                    .is_distinct_from(
                        teacher_staff_member_id
                    ),
                )
            )
        )

        stmt = (
            select(
                own_group_exists
                & ~foreign_group_exists
            )
            .select_from(
                Assessment
            )
            .where(
                Assessment.id
                == assessment_id,

                Assessment.school_id
                == school_id,
            )
        )

        result = await db.execute(
            stmt
        )

        value = result.scalar_one_or_none()

        return bool(
            value
        )

    # =====================================================
    # SCHOOL ORGANIZATION SNAPSHOT
    # =====================================================

    @staticmethod
    async def get_school_org_snapshot(
            db: AsyncSession,
            *,
            school_id: int,
    ):
        """
        Получить текущую организационную принадлежность школы
        для фиксации в AssessmentQualitySummary.

        Snapshot используется только на момент завершения
        Assessment.
        """

        stmt = (
            select(
                School.id.label(
                    "school_id"
                ),
                School.district_id.label(
                    "district_id"
                ),
                District.region_id.label(
                    "region_id"
                ),
            )
            .select_from(
                School
            )
            .outerjoin(
                District,
                District.id
                == School.district_id,
            )
            .where(
                School.id == school_id,
            )
        )

        result = await db.execute(
            stmt
        )

        return result.one_or_none()
