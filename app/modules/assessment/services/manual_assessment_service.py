# app/modules/assessment/services/manual_assessment_service.py

from __future__ import annotations

from decimal import Decimal
from app.modules.assessment.helpers.assessment_names import manual_names, localized, VERSION
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.enums import (
    AssessmentInputMode,
    AssessmentMode,
    AssessmentParticipationStatus,
    AssessmentStatus,
)
from app.modules.assessment.models import (
    Assessment,
    AssessmentGroup,
    AssessmentObjective,
    AssessmentStudent,
)
from app.modules.assessment.repositories.assessment_objective_repo import (
    AssessmentObjectiveRepo,
    AssessmentObjectiveResultWrite,
)
from app.modules.assessment.repositories.assessment_repo import (
    AssessmentRepo,
)
from app.modules.assessment.repositories.assessment_result_repo import (
    AssessmentResultRepo,
    AssessmentResultWrite,
)
from app.modules.assessment.repositories.assessment_student_repo import AssessmentStudentRepo
from app.modules.assessment.schemas.assessment_create_schemas import (
    AssessmentCreateDTO,
)
from app.modules.assessment.schemas.manual_result_schemas import (
    ManualAssessmentGroupDTO,
    ManualAssessmentPageDTO,
    ManualAssessmentObjectiveDTO,
    ManualAssessmentSaveDTO,
    ManualAssessmentStudentRowDTO,
    ManualStudentObjectiveResultDTO,
)
from app.modules.assessment.services.assessment_scoring_service import (
    AssessmentScoringService,
)
from app.modules.education.models import (
    SchoolClass,
    SchoolStudentEnrollment,
)
from app.modules.education.repositories.class_subject_teacher_repo import SchoolClassSubjectTeacherRepo
from app.modules.education.repositories.enrollment_repo import (
    SchoolStudentEnrollmentRepo,
)
from app.modules.education.repositories.school_class_repo import (
    SchoolClassRepo,
)
from app.modules.education.repositories.subject_repo import (
    SubjectRepo,
)


class ManualAssessmentService:
    """
    Бизнес-логика ручного Assessment.

    Ответственность сервиса:

        - проверить школу;
        - проверить предмет;
        - проверить выбранные классы;
        - создать Assessment;
        - создать AssessmentGroup;
        - зафиксировать состав учащихся;
        - создать AssessmentObjective;
        - сохранить ручные результаты;
        - рассчитать процент и оценку.

    Repository Layer:
        только выполняет SQL / ORM операции.

    AssessmentScoringService:
        является единственным источником правил
        расчёта процентов и оценок.
    """

    @staticmethod
    def _resolve_duration_minutes(
            *,
            duration_minutes: int | None,
    ) -> int | None:
        """
        Определить длительность Assessment.

        Длительность задаёт учитель.
        """

        if duration_minutes is None:
            return None

        if duration_minutes <= 0:
            raise ValueError(
                "Продолжительность Assessment "
                "должна быть больше 0 минут."
            )

        return duration_minutes

    # =====================================================
    # CREATE
    # =====================================================

    @classmethod
    async def create_assessment(
            cls,
            db: AsyncSession,
            *,
            dto: AssessmentCreateDTO,
    ) -> int:
        """
        Создать Assessment ручного режима.

        Один Assessment:
            - принадлежит одной школе;
            - относится к одному предмету;
            - может содержать несколько классов;
            - может входить в AssessmentCampaign;
            - может использовать учебные цели;
            - фиксирует преподавателя предмета
              отдельно для каждой AssessmentGroup.

        Важно:

            created_by_user_id
                = кто создал Assessment.

            AssessmentGroup.teacher_staff_member_id
                = фактический преподаватель предмета
                  в конкретном классе.

        Эти понятия намеренно разделены.

        Алгоритм:

            1. Проверить DTO.
            2. Определить duration_minutes.
            3. Проверить предмет.
            4. Проверить campaign.
            5. Проверить классы.
            6. Проверить учебный год campaign.
            7. Получить преподавателей всех классов
               одним SQL-запросом.
            8. Проверить учебные цели.
            9. Создать Assessment.
            10. Создать AssessmentGroup
                с teacher snapshot.
            11. Получить контингент классов.
            12. Создать AssessmentStudent.
            13. Создать AssessmentObjective.
            14. commit.
        """

        # =====================================================
        # VALIDATE DTO
        # =====================================================

        cls._validate_create_dto(
            dto
        )

        # =====================================================
        # RESOLVE DURATION
        # =====================================================

        duration_minutes = (
            cls._resolve_duration_minutes(
                duration_minutes=(
                    dto.duration_minutes
                ),
            )
        )

        # =====================================================
        # SUBJECT
        # =====================================================

        subject = (
            await SubjectRepo.get_active_by_id(
                db,
                subject_id=(
                    dto.subject_id
                ),
            )
        )

        if subject is None:
            raise ValueError(
                "Таңдалған пән табылмады "
                "немесе белсенді емес."
            )

        # =====================================================
        # CAMPAIGN
        # =====================================================

        campaign = None

        if dto.campaign_id is not None:
            campaign = (
                await AssessmentRepo
                .get_campaign_by_id_for_school(
                    db,
                    campaign_id=(
                        dto.campaign_id
                    ),
                    school_id=(
                        dto.school_id
                    ),
                )
            )

            if campaign is None:
                raise ValueError(
                    "Assessment кампаниясы табылмады "
                    "немесе басқа мектепке тиесілі."
                )

        # =====================================================
        # CLASSES
        # =====================================================

        classes = (
            await SchoolClassRepo
            .get_many_by_ids_for_school(
                db,
                school_id=(
                    dto.school_id
                ),
                class_ids=(
                    dto.school_class_ids
                ),
            )
        )

        cls._validate_classes(
            requested_class_ids=(
                dto.school_class_ids
            ),
            classes=(
                classes
            ),
        )

        # =====================================================
        # CAMPAIGN ACADEMIC YEAR
        # =====================================================

        if campaign is not None:
            invalid_classes = [
                school_class.name
                for school_class in classes
                if (
                        school_class.academic_year_start
                        != campaign.academic_year_start
                )
            ]

            if invalid_classes:
                raise ValueError(
                    "Бағалау үдерісінің оқу жылы "
                    "таңдалған сыныптардың оқу жылымен "
                    "сәйкес келмейді: "
                    + ", ".join(
                        invalid_classes
                    )
                )

        # =====================================================
        # CHECKPOINT
        # =====================================================

        if dto.checkpoint is not None:

            # Официальная контрольная точка относится
            # к конкретному учебному году.
            academic_year_starts = {
                school_class.academic_year_start
                for school_class in classes
            }

            if len(academic_year_starts) != 1:
                raise ValueError(
                    "Жылдық динамикаға арналған бағалау "
                    "тек бір оқу жылының сыныптарын қамтуы тиіс."
                )

            academic_year_start = next(
                iter(
                    academic_year_starts
                )
            )

            conflicting_class_ids = (
                await AssessmentRepo
                .get_checkpoint_conflicting_class_ids(
                    db,
                    school_id=(
                        dto.school_id
                    ),
                    subject_id=(
                        dto.subject_id
                    ),
                    academic_year_start=(
                        academic_year_start
                    ),
                    checkpoint=(
                        dto.checkpoint
                    ),
                    school_class_ids=(
                        dto.school_class_ids
                    ),
                )
            )

            if conflicting_class_ids:
                conflicting_class_names = sorted(
                    school_class.name
                    for school_class in classes
                    if (
                        school_class.id
                        in conflicting_class_ids
                    )
                )

                raise ValueError(
                    "Таңдалған бақылау нүктесі осы пән бойынша "
                    "келесі сыныптарда бұрыннан қолданылған: "
                    + ", ".join(
                        conflicting_class_names
                    )
                    + "."
                )
            
        # =====================================================
        # CLASS / SUBJECT / TEACHER ASSIGNMENTS
        # =====================================================

        teacher_assignments = (
            await SchoolClassSubjectTeacherRepo
            .get_active_primary_for_classes(
                db,
                school_id=(
                    dto.school_id
                ),
                subject_id=(
                    dto.subject_id
                ),
                school_class_ids=(
                    dto.school_class_ids
                ),
            )
        )

        # Один SQL уже выполнен.
        # Далее только lookup в памяти.
        assignment_by_class_id = {
            assignment.school_class_id: assignment
            for assignment in teacher_assignments
        }

        missing_teacher_classes = [
            school_class.name
            for school_class in classes
            if school_class.id not in assignment_by_class_id
        ]

        if missing_teacher_classes:
            raise ValueError(
                "Таңдалған пән бойынша негізгі мұғалім "
                "тағайындалмаған сыныптар: "
                + ", ".join(
                    missing_teacher_classes
                )
            )

        # =====================================================
        # LEARNING OBJECTIVES
        # =====================================================

        learning_objectives = []

        if dto.objectives:
            learning_objective_ids = tuple(
                item.learning_objective_id
                for item in dto.objectives
            )

            learning_objectives = (
                await AssessmentRepo
                .get_learning_objectives_by_ids(
                    db,
                    learning_objective_ids=(
                        learning_objective_ids
                    ),
                    subject_id=(
                        dto.subject_id
                    ),
                )
            )

            cls._validate_learning_objectives(
                dto=dto,
                classes=classes,
                learning_objectives=(
                    learning_objectives
                ),
            )

        # =====================================================
        # CREATE TRANSACTION
        # =====================================================

        try:
            # =================================================
            # ASSESSMENT
            # =================================================

            naming=manual_names(dto,subject,classes)
            assessment = Assessment(
                school_id=(
                    dto.school_id
                ),

                campaign_id=(
                    dto.campaign_id
                ),

                subject_id=(
                    dto.subject_id
                ),

                created_by_user_id=(
                    dto.created_by_user_id
                ),

                settings=naming,
                title=(
                    naming[VERSION]["ru"]
                ),

                description=(
                    dto.description.strip()
                    if dto.description
                    else None
                ),

                subject_name_snapshot=(
                    subject.name_kz
                ),

                assessment_type=(
                    dto.assessment_type
                ),

                assessment_mode=(
                    dto.assessment_mode
                ),

                checkpoint=(
                    dto.checkpoint
                ),

                input_mode=(
                    AssessmentInputMode.MANUAL
                ),

                status=(
                    AssessmentStatus.DRAFT
                ),

                max_score=(
                    dto.max_score
                ),

                duration_minutes=(
                    duration_minutes
                ),
            )

            await AssessmentRepo.create(
                db,
                assessment=assessment,
            )

            # =================================================
            # GROUPS
            # =================================================

            groups: list[
                AssessmentGroup
            ] = []

            for school_class in classes:
                teacher_assignment = (
                    assignment_by_class_id[
                        school_class.id
                    ]
                )

                groups.append(
                    AssessmentGroup(
                        school_id=(
                            dto.school_id
                        ),

                        assessment_id=(
                            assessment.id
                        ),

                        school_class_id=(
                            school_class.id
                        ),

                        class_name_snapshot=(
                            school_class.name
                        ),

                        grade_level_snapshot=(
                            school_class.grade_level
                        ),

                        academic_year_start_snapshot=(
                            school_class
                            .academic_year_start
                        ),

                        teacher_staff_member_id=(
                            teacher_assignment
                            .staff_member_id
                        ),

                        teacher_name_snapshot=(
                            teacher_assignment
                            .teacher_name_snapshot
                        ),
                    )
                )

            groups = (
                await AssessmentRepo.add_groups(
                    db,
                    groups=groups,
                )
            )

            group_by_class_id = {
                group.school_class_id: group
                for group in groups
            }

            # =================================================
            # STUDENTS
            # =================================================

            enrollments = (
                await SchoolStudentEnrollmentRepo
                .get_active_by_classes(
                    db,
                    school_id=(
                        dto.school_id
                    ),
                    school_class_ids=(
                        dto.school_class_ids
                    ),
                )
            )

            assessment_students = (
                cls._build_assessment_students(
                    school_id=(
                        dto.school_id
                    ),
                    enrollments=(
                        enrollments
                    ),
                    group_by_class_id=(
                        group_by_class_id
                    ),
                )
            )

            await AssessmentStudentRepo.add_many(
                db,
                students=assessment_students,
            )

            # =================================================
            # OBJECTIVES
            # =================================================

            if dto.objectives:
                objective_by_id = {
                    objective.id: objective
                    for objective
                    in learning_objectives
                }

                assessment_objectives: list[
                    AssessmentObjective
                ] = []

                for objective_input in dto.objectives:
                    objective = objective_by_id[
                        objective_input
                        .learning_objective_id
                    ]

                    assessment_objectives.append(
                        AssessmentObjective(
                            assessment_id=(
                                assessment.id
                            ),

                            learning_objective_id=(
                                objective.id
                            ),

                            code_snapshot=(
                                objective.code
                            ),

                            title_snapshot=(
                                objective.title_kz
                            ),

                            max_score=(
                                objective_input
                                .max_score
                            ),

                            order_no=(
                                objective_input
                                .order_no
                            ),
                        )
                    )

                await AssessmentRepo.add_objectives(
                    db,
                    objectives=(
                        assessment_objectives
                    ),
                )

            # =================================================
            # COMMIT
            # =================================================

            assessment_id = (
                assessment.id
            )

            await db.commit()

            return assessment_id

        except Exception:
            await db.rollback()
            raise

    # =====================================================
    # SAVE MANUAL RESULTS
    # =====================================================

    @classmethod
    async def save_results(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            dto: ManualAssessmentSaveDTO,
    ) -> None:
        """
        Сохранить ручные результаты Assessment
        от имени staff/admin.

        Staff/admin имеет доступ ко всем
        AssessmentGroup выбранного Assessment.
        """

        # =====================================================
        # ASSESSMENT
        # =====================================================

        assessment = (
            await AssessmentRepo.get_by_id_for_school(
                db,
                assessment_id=dto.assessment_id,
                school_id=school_id,
            )
        )

        if assessment is None:
            raise ValueError(
                "Assessment не найден."
            )

        # =====================================================
        # PARTICIPANTS
        # =====================================================

        participants = await AssessmentStudentRepo.get_many_for_assessment(
            db,
            assessment_id=assessment.id,
            school_id=school_id,
        )

        # =====================================================
        # COMMON SAVE
        # =====================================================

        await cls._save_results_internal(
            db,
            assessment=assessment,
            participants=participants,
            dto=dto,
        )

    @classmethod
    async def save_teacher_results(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            dto: ManualAssessmentSaveDTO,
    ) -> None:
        """
        Сохранить ручные результаты Assessment
        от имени текущего учителя.

        Teacher может изменять результаты только
        участников AssessmentGroup, закреплённых
        за его teacher_staff_member_id.

        Security boundary:
            school_id
            teacher_staff_member_id
            assessment_id
        """

        if school_id <= 0:
            raise ValueError(
                "Некорректный school_id."
            )

        if teacher_staff_member_id <= 0:
            raise ValueError(
                "Некорректный teacher_staff_member_id."
            )

        # =====================================================
        # ASSESSMENT + TEACHER ACCESS
        # =====================================================

        assessment = (
            await AssessmentRepo
            .get_for_teacher_manual_entry(
                db,
                assessment_id=dto.assessment_id,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
            )
        )

        if assessment is None:
            raise ValueError(
                "Assessment не найден "
                "или недоступен текущему учителю."
            )

        # =====================================================
        # TEACHER PARTICIPANTS
        # =====================================================

        participants = (
            await AssessmentStudentRepo
            .get_many_for_teacher_assessment(
                db,
                assessment_id=assessment.id,
                school_id=school_id,
                teacher_staff_member_id=teacher_staff_member_id,
            )
        )

        # =====================================================
        # COMMON SAVE
        # =====================================================

        await cls._save_results_internal(
            db,
            assessment=assessment,
            participants=participants,
            dto=dto,
        )

    @classmethod
    async def _save_results_internal(
            cls,
            db: AsyncSession,
            *,
            assessment: Assessment,
            participants: list[AssessmentStudent],
            dto: ManualAssessmentSaveDTO,
    ) -> None:
        """
        Общая бизнес-логика сохранения ручных результатов.

        Метод не определяет права доступа.

        Public service methods обязаны заранее передать
        разрешённый набор participants:

            staff/admin
                -> все участники Assessment;

            teacher
                -> только участники его AssessmentGroup.

        SQL-запросов внутри цикла по ученикам нет.
        """

        # =====================================================
        # STATE
        # =====================================================

        cls._validate_manual_assessment_state(
            assessment
        )

        if (
                assessment.max_score is None
                or assessment.max_score <= 0
        ):
            raise ValueError(
                "Для ввода результатов необходимо указать "
                "положительный максимальный балл."
            )

        assessment_max_score = cast(
            Decimal,
            assessment.max_score,
        )

        # =====================================================
        # PAYLOAD
        # =====================================================

        cls._validate_result_payload(
            dto
        )

        # =====================================================
        # PARTICIPANT SECURITY BOUNDARY
        # =====================================================

        participant_by_id = {
            participant.id: participant
            for participant in participants
        }

        submitted_ids = {
            item.assessment_student_id
            for item in dto.results
        }

        unknown_ids = (
                submitted_ids
                - participant_by_id.keys()
        )

        if unknown_ids:
            raise ValueError(
                "Обнаружены участники, которые "
                "не относятся к доступным группам "
                "выбранного Assessment."
            )

        # =====================================================
        # ASSESSMENT MODE
        # =====================================================

        objective_mode = (
                assessment.assessment_mode
                in {
                    AssessmentMode.BY_OBJECTIVES,
                    AssessmentMode.ASSESSMENT_BY_SECTION,
                    AssessmentMode.ASSESSMENT_BY_QUARTER,
                }
        )

        objective_by_id: dict[
            int,
            AssessmentObjective,
        ] = {}

        expected_objective_ids: set[int] = set()

        # =====================================================
        # OBJECTIVE STRUCTURE
        # =====================================================

        if objective_mode:
            objectives = (
                await AssessmentObjectiveRepo
                .get_many_by_assessment_id(
                    db,
                    assessment_id=assessment.id,
                )
            )

            if not objectives:
                raise ValueError(
                    "Assessment оқу мақсаттарымен құрылған, "
                    "бірақ оқу мақсаттары табылмады."
                )

            objective_by_id = {
                objective.id: objective
                for objective in objectives
            }

            expected_objective_ids = set(
                objective_by_id
            )

            objective_max_total = sum(
                (
                    cast(
                        Decimal,
                        objective.max_score,
                    )
                    for objective in objectives
                ),
                Decimal("0"),
            )

            if (
                    objective_max_total
                    != assessment_max_score
            ):
                raise ValueError(
                    "Assessment оқу мақсаттарының максималды "
                    "баллдарының қосындысы Assessment максималды "
                    "баллына тең емес."
                )

        elif (
                assessment.assessment_mode
                != AssessmentMode.WITHOUT_OBJECTIVES
        ):
            raise ValueError(
                "Неизвестный режим Assessment."
            )

        # =====================================================
        # WRITE BUFFERS
        # =====================================================

        result_writes: list[
            AssessmentResultWrite
        ] = []

        delete_student_ids: list[int] = []

        # Пока AssessmentResult.id ещё не известен
        # для новых строк, сохраняем рассчитанные
        # objective-данные по AssessmentStudent.id.

        objective_writes_by_student_id: dict[
            int,
            tuple[
                tuple[
                    int,
                    Decimal,
                    Decimal,
                    Decimal,
                ],
                ...,
            ],
        ] = {}

        try:
            # =================================================
            # VALIDATE + CALCULATE IN MEMORY
            # =================================================

            for item in dto.results:
                participant = participant_by_id[
                    item.assessment_student_id
                ]

                # =============================================
                # NOT COMPLETED
                # =============================================

                if (
                        item.participation_status
                        != AssessmentParticipationStatus.COMPLETED
                ):
                    cls._validate_non_completed_result(
                        score=item.score,
                        objective_scores=(
                            item.objective_scores
                        ),
                    )

                    participant.participation_status = (
                        item.participation_status
                    )

                    delete_student_ids.append(
                        participant.id
                    )

                    continue

                # =============================================
                # COMPLETED
                # =============================================

                participant.participation_status = (
                    AssessmentParticipationStatus.COMPLETED
                )

                # =============================================
                # WITHOUT OBJECTIVES
                # =============================================

                if (
                        assessment.assessment_mode
                        == AssessmentMode.WITHOUT_OBJECTIVES
                ):
                    cls._validate_without_objectives_result(
                        score=item.score,
                        objective_scores=(
                            item.objective_scores
                        ),
                        max_score=(
                            assessment_max_score
                        ),
                    )

                    assert item.score is not None

                    scoring = (
                        AssessmentScoringService.calculate(
                            score=item.score,
                            max_score=(
                                assessment_max_score
                            ),
                        )
                    )

                    result_writes.append(
                        AssessmentResultWrite(
                            assessment_student_id=(
                                participant.id
                            ),
                            score=scoring.score,
                            max_score=scoring.max_score,
                            percent=scoring.percent,
                            grade=scoring.grade,
                        )
                    )

                    continue

                # =============================================
                # OBJECTIVES
                # =============================================

                cls._validate_objective_result(
                    direct_score=item.score,
                    objective_scores=(
                        item.objective_scores
                    ),
                    objective_by_id=(
                        objective_by_id
                    ),
                    expected_objective_ids=(
                        expected_objective_ids
                    ),
                )

                total_score = sum(
                    (
                        objective_score.score
                        for objective_score
                        in item.objective_scores
                    ),
                    Decimal("0"),
                )

                if (
                        total_score
                        > assessment_max_score
                ):
                    raise ValueError(
                        "Оқу мақсаттары бойынша жиналған "
                        "жалпы балл Assessment максималды "
                        "баллынан асып кетті."
                    )

                total_scoring = (
                    AssessmentScoringService.calculate(
                        score=total_score,
                        max_score=(
                            assessment_max_score
                        ),
                    )
                )

                result_writes.append(
                    AssessmentResultWrite(
                        assessment_student_id=(
                            participant.id
                        ),
                        score=(
                            total_scoring.score
                        ),
                        max_score=(
                            total_scoring.max_score
                        ),
                        percent=(
                            total_scoring.percent
                        ),
                        grade=(
                            total_scoring.grade
                        ),
                    )
                )

                # =============================================
                # OBJECTIVE RESULTS
                # =============================================

                calculated_objectives: list[
                    tuple[
                        int,
                        Decimal,
                        Decimal,
                        Decimal,
                    ]
                ] = []

                for objective_score in (
                        item.objective_scores
                ):
                    objective = objective_by_id[
                        objective_score
                        .assessment_objective_id
                    ]

                    objective_max_score = cast(
                        Decimal,
                        objective.max_score,
                    )

                    objective_scoring = (
                        AssessmentScoringService
                        .calculate(
                            score=(
                                objective_score.score
                            ),
                            max_score=(
                                objective_max_score
                            ),
                        )
                    )

                    calculated_objectives.append(
                        (
                            objective.id,
                            objective_scoring.score,
                            objective_scoring.max_score,
                            objective_scoring.percent,
                        )
                    )

                objective_writes_by_student_id[
                    participant.id
                ] = tuple(
                    calculated_objectives
                )

            # =================================================
            # BATCH DELETE NON-COMPLETED RESULTS
            # =================================================

            if delete_student_ids:
                await AssessmentResultRepo.delete_many_by_student_ids(db, assessment_student_ids=delete_student_ids)
            # =================================================
            # BATCH UPSERT TOTAL RESULTS
            # =================================================

            result_by_student_id = (
                await AssessmentResultRepo
                .upsert_many(
                    db,
                    items=result_writes,
                )
            )

            completed_result_ids = [
                result.id
                for result
                in result_by_student_id.values()
            ]

            # =================================================
            # BATCH REPLACE OBJECTIVE RESULTS
            # =================================================

            if objective_mode:
                objective_result_writes: list[
                    AssessmentObjectiveResultWrite
                ] = []

                for (
                        student_id,
                        calculated_rows,
                ) in (
                        objective_writes_by_student_id.items()
                ):
                    assessment_result = (
                        result_by_student_id[
                            student_id
                        ]
                    )

                    for (
                            assessment_objective_id,
                            score,
                            max_score,
                            percent,
                    ) in calculated_rows:
                        objective_result_writes.append(
                            AssessmentObjectiveResultWrite(
                                assessment_result_id=(
                                    assessment_result.id
                                ),
                                assessment_objective_id=(
                                    assessment_objective_id
                                ),
                                score=score,
                                max_score=max_score,
                                percent=percent,
                            )
                        )

                await AssessmentObjectiveRepo.replace_results(db, assessment_result_ids=completed_result_ids,
                                                              results=objective_result_writes,
                                                              )

            elif completed_result_ids:
                # Защита от устаревших objective rows,
                # если legacy/test Assessment был
                # переведён в WITHOUT_OBJECTIVES.

                await AssessmentObjectiveRepo.replace_results(db, assessment_result_ids=completed_result_ids,
                                                              results=(),
                                                              )

            # =================================================
            # COMMIT
            # =================================================

            await db.commit()

        except Exception:
            await db.rollback()
            raise

    # =====================================================
    # PAGE DATA
    # =====================================================

    @classmethod
    async def get_manual_entry_page(
            cls,
            db: AsyncSession,
            *,
            assessment_id: int,
            school_id: int,
    ) -> ManualAssessmentPageDTO:
        """
        Собрать DTO страницы ручного ввода
        для staff/admin.
        """

        assessment = (
            await AssessmentRepo.get_for_manual_entry(
                db,
                assessment_id=assessment_id,
                school_id=school_id,
            )
        )

        if assessment is None:
            raise ValueError(
                "Assessment не найден."
            )

        return cls._build_manual_entry_page_dto(
            assessment
        )

    @classmethod
    async def get_teacher_manual_entry_page(
            cls,
            db: AsyncSession,
            *,
            assessment_id: int,
            school_id: int,
            teacher_staff_member_id: int,
    ) -> ManualAssessmentPageDTO:
        """
        Собрать DTO страницы ручного ввода
        Assessment текущего учителя.

        Repository возвращает только AssessmentGroup,
        закреплённые за текущим teacher.

        Security boundary:
            school_id
            teacher_staff_member_id
            assessment_id
        """

        if school_id <= 0:
            raise ValueError(
                "Некорректный school_id."
            )

        if teacher_staff_member_id <= 0:
            raise ValueError(
                "Некорректный teacher_staff_member_id."
            )

        assessment = (
            await AssessmentRepo
            .get_for_teacher_manual_entry(
                db,
                assessment_id=assessment_id,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
            )
        )

        if assessment is None:
            raise ValueError(
                "Assessment не найден "
                "или недоступен текущему учителю."
            )

        return cls._build_manual_entry_page_dto(
            assessment
        )

    @classmethod
    def _build_manual_entry_page_dto(
            cls,
            assessment: Assessment,
    ) -> ManualAssessmentPageDTO:
        """
        Собрать ManualAssessmentPageDTO
        из заранее eager-loaded Assessment.

        Дополнительных SQL-запросов
        внутри метода быть не должно.
        """

        if (
                assessment.input_mode
                != AssessmentInputMode.MANUAL
        ):
            raise ValueError(
                "Assessment не предназначен "
                "для ручного ввода результатов."
            )

        objective_mode = (
                assessment.assessment_mode
                in {
                    AssessmentMode.BY_OBJECTIVES,
                    AssessmentMode.ASSESSMENT_BY_SECTION,
                    AssessmentMode.ASSESSMENT_BY_QUARTER,
                }
        )

        # =====================================================
        # OBJECTIVES
        # =====================================================

        page_objectives: tuple[
            ManualAssessmentObjectiveDTO,
            ...,
        ]

        if objective_mode:
            page_objectives = tuple(
                ManualAssessmentObjectiveDTO(
                    assessment_objective_id=(
                        objective.id
                    ),

                    learning_objective_id=(
                        objective.learning_objective_id
                    ),

                    code=(
                        objective.code_snapshot
                    ),

                    title=(
                        objective.title_snapshot
                    ),

                    max_score=cast(
                        Decimal,
                        objective.max_score,
                    ),

                    order_no=(
                        objective.order_no
                    ),
                )
                for objective
                in assessment.objectives
            )

        else:
            page_objectives = ()

        # =====================================================
        # GROUPS
        # =====================================================

        groups: list[
            ManualAssessmentGroupDTO
        ] = []

        for group in assessment.groups:
            student_rows: list[
                ManualAssessmentStudentRowDTO
            ] = []

            sorted_students = sorted(
                group.students,
                key=lambda item: (
                    item.student.last_name,
                    item.student.first_name,
                    item.student.middle_name or "",
                    item.student.id,
                ),
            )

            for participant in sorted_students:
                result = participant.result

                existing_objective_by_id = {
                    objective_result.assessment_objective_id: (
                        objective_result
                    )
                    for objective_result in (
                        result.objective_results
                        if result is not None
                        else ()
                    )
                }

                student_objective_results: tuple[
                    ManualStudentObjectiveResultDTO,
                    ...,
                ]

                if objective_mode:
                    student_objective_results = tuple(
                        ManualStudentObjectiveResultDTO(
                            assessment_objective_id=(
                                objective.id
                            ),

                            score=(
                                existing.score
                                if existing is not None
                                else None
                            ),

                            max_score=(
                                existing.max_score
                                if existing is not None
                                else cast(
                                    Decimal,
                                    objective.max_score,
                                )
                            ),

                            percent=(
                                existing.percent
                                if existing is not None
                                else None
                            ),
                        )
                        for objective
                        in assessment.objectives
                        for existing in (
                            existing_objective_by_id.get(
                                objective.id
                            ),
                        )
                    )

                else:
                    student_objective_results = ()

                student_rows.append(
                    ManualAssessmentStudentRowDTO(
                        assessment_student_id=(
                            participant.id
                        ),

                        student_id=(
                            participant.student_id
                        ),

                        student_name=(
                            participant
                            .student_name_snapshot
                        ),

                        participation_status=(
                            participant
                            .participation_status
                            .value
                        ),

                        participation_status_label=(
                            participant
                            .participation_status
                            .label_kz
                        ),

                        score=(
                            result.score
                            if result is not None
                            else None
                        ),

                        percent=(
                            result.percent
                            if result is not None
                            else None
                        ),

                        grade=(
                            result.grade.value
                            if result is not None
                            else None
                        ),

                        grade_label=(
                            result.grade.label_kz
                            if result is not None
                            else None
                        ),

                        objective_results=(
                            student_objective_results
                        ),
                    )
                )

            groups.append(
                ManualAssessmentGroupDTO(
                    assessment_group_id=(
                        group.id
                    ),

                    school_class_id=(
                        group.school_class_id
                    ),

                    class_name=(
                        group.class_name_snapshot
                    ),

                    academic_year_start=(
                        group
                        .academic_year_start_snapshot
                    ),

                    teacher_name=(
                        group.teacher_name_snapshot
                    ),

                    students=tuple(
                        student_rows
                    ),
                )
            )

        groups.sort(
            key=lambda item: (
                item.academic_year_start,
                item.class_name,
                item.assessment_group_id,
            )
        )

        # =====================================================
        # PAGE DTO
        # =====================================================

        return ManualAssessmentPageDTO(
            assessment_id=(
                assessment.id
            ),

            title=(
                localized(assessment)
            ),

            description=(
                assessment.description
            ),

            subject_id=(
                assessment.subject_id
            ),

            subject_name=(
                    assessment.subject_name_snapshot
                    or assessment.subject.name_kz
            ),

            max_score=(
                assessment.max_score
            ),

            assessment_type=(
                assessment.assessment_type.value
            ),

            assessment_type_label=(
                assessment
                .assessment_type
                .label_kz
            ),

            assessment_mode=(
                assessment.assessment_mode.value
            ),

            duration_minutes=(
                assessment.duration_minutes
            ),

            status=(
                assessment.status.value
            ),

            status_label=(
                assessment.status.label_kz
            ),

            objectives=(
                page_objectives
            ),

            groups=tuple(
                groups
            ),
        )

    # =====================================================
    # CREATE VALIDATION
    # =====================================================

    @staticmethod
    def _validate_create_dto(
            dto: AssessmentCreateDTO,
    ) -> None:
        """
        Базовая валидация данных создания Assessment.

        Главный источник структуры Assessment:
            dto.assessment_mode
        """

        # =====================================================
        # SCOPE
        # =====================================================

        if dto.school_id <= 0:
            raise ValueError(
                "Некорректный school_id."
            )

        if (
                dto.campaign_id is not None
                and dto.campaign_id <= 0
        ):
            raise ValueError(
                "Некорректный campaign_id."
            )

        if (
                dto.campaign_id is not None
                and dto.assessment_mode
                != AssessmentMode.WITHOUT_OBJECTIVES
        ):
            raise ValueError(
                "Бағалау үдерісі әзірге тек "
                "диагностикалық режиміндегі "
                "бағалау үшін қолданылады."
            )

        if dto.subject_id <= 0:
            raise ValueError(
                "Некорректный subject_id."
            )

        if dto.created_by_user_id <= 0:
            raise ValueError(
                "Некорректный created_by_user_id."
            )

        # =====================================================
        # CONTENT
        # =====================================================

        if len(dto.title.strip())>255:
            raise ValueError(
                "Комментарий слишком длинный."
            )

        # =====================================================
        # CLASSES
        # =====================================================

        if not dto.school_class_ids:
            raise ValueError(
                "Необходимо выбрать хотя бы один класс."
            )

        if len(set(dto.school_class_ids)) != len(dto.school_class_ids):
            raise ValueError(
                "Список классов содержит дубликаты."
            )

        for school_class_id in dto.school_class_ids:
            if school_class_id <= 0:
                raise ValueError(
                    "Некорректный school_class_id."
                )

        # =====================================================
        # MAX SCORE
        # =====================================================

        if dto.max_score is not None:
            if dto.max_score <= 0:
                raise ValueError(
                    "Максимальный балл "
                    "должен быть больше 0."
                )

        # =====================================================
        # DURATION
        # =====================================================

        if dto.duration_minutes is not None:
            if dto.duration_minutes <= 0:
                raise ValueError(
                    "Продолжительность Assessment "
                    "должна быть больше 0 минут."
                )

        # =====================================================
        # ASSESSMENT MODE
        # =====================================================

        if (
                dto.assessment_mode
                == AssessmentMode.WITHOUT_OBJECTIVES
        ):
            if dto.objectives:
                raise ValueError(
                    "Assessment в режиме "
                    "WITHOUT_OBJECTIVES не должен "
                    "содержать учебные цели."
                )

        elif dto.assessment_mode in {
            AssessmentMode.BY_OBJECTIVES,
                    AssessmentMode.ASSESSMENT_BY_SECTION,
            AssessmentMode.ASSESSMENT_BY_QUARTER,
        }:
            if not dto.objectives:
                raise ValueError(
                    "Для БЖБ/ТЖБ Assessment "
                    "необходимо выбрать "
                    "хотя бы одну учебную цель."
                )

        else:
            raise ValueError(
                "Неизвестный режим Assessment."
            )

        # =====================================================
        # OBJECTIVES
        # =====================================================

        if not dto.objectives:
            return

        orders = [
            item.order_no
            for item in dto.objectives
        ]

        objective_ids = [
            item.learning_objective_id
            for item in dto.objectives
        ]

        if len(set(orders)) != len(orders):
            raise ValueError(
                "Порядок учебных целей "
                "содержит дубликаты."
            )

        if len(set(objective_ids)) != len(objective_ids):
            raise ValueError(
                "Учебные цели содержат дубликаты."
            )

        for item in dto.objectives:
            if item.learning_objective_id <= 0:
                raise ValueError(
                    "Некорректный learning_objective_id."
                )

            if item.order_no <= 0:
                raise ValueError(
                    "order_no должен быть больше 0."
                )

            if item.max_score <= 0:
                raise ValueError(
                    "Максимальный балл учебной цели "
                    "должен быть больше 0."
                )

        if dto.max_score is None:
            raise ValueError(
                "Для Assessment с учебными целями "
                "необходимо указать max_score."
            )

        objective_total = sum(
            (
                item.max_score
                for item in dto.objectives
            ),
            Decimal("0"),
        )

        if objective_total != dto.max_score:
            raise ValueError(
                "Сумма максимальных баллов "
                "учебных целей должна быть равна "
                "максимальному баллу Assessment."
            )

    # =====================================================
    # CLASS VALIDATION
    # =====================================================

    @staticmethod
    def _validate_classes(
            *,
            requested_class_ids: tuple[int, ...],
            classes: list[SchoolClass],
    ) -> None:
        requested = set(
            requested_class_ids
        )

        found = {
            school_class.id
            for school_class in classes
        }

        if requested != found:
            raise ValueError(
                "Один или несколько выбранных классов "
                "не найдены в этой школе."
            )

        inactive = [
            school_class.name
            for school_class in classes
            if not school_class.is_active
        ]

        if inactive:
            raise ValueError(
                "Нельзя использовать неактивные классы: "
                + ", ".join(inactive)
            )

    # =====================================================
    # OBJECTIVE VALIDATION
    # =====================================================

    @staticmethod
    def _validate_learning_objectives(
            *,
            dto: AssessmentCreateDTO,
            classes: list[SchoolClass],
            learning_objectives,
    ) -> None:
        requested_ids = {
            item.learning_objective_id
            for item in dto.objectives
        }

        found_ids = {
            objective.id
            for objective in learning_objectives
        }

        if requested_ids != found_ids:
            raise ValueError(
                "Одна или несколько учебных целей "
                "не найдены либо относятся "
                "к другому предмету."
            )

        class_grade_levels = {
            school_class.grade_level
            for school_class in classes
        }

        allowed_grade_levels = {g-1 for g in class_grade_levels} if dto.assessment_type.value=='baseline' else class_grade_levels

        if dto.assessment_mode in (AssessmentMode.ASSESSMENT_BY_SECTION,AssessmentMode.ASSESSMENT_BY_QUARTER):
            if dto.quarter not in (1,2,3,4) or any(objective.quarter!=dto.quarter for objective in learning_objectives):
                raise ValueError('Выберите учебные цели выбранной четверти. / Таңдалған тоқсанның оқу мақсаттарын таңдаңыз.')

        objective_grade_levels = {
            objective.grade_level
            for objective in learning_objectives
        }

        if not objective_grade_levels.issubset(
                allowed_grade_levels
        ):
            raise ValueError(
                "Учебные цели не соответствуют "
                "параллели выбранных классов."
            )

        # AssessmentObjective является общей структурой
        # для всей работы. Поэтому пока при использовании
        # целей Assessment должен охватывать одну параллель.
        if len(class_grade_levels) > 1:
            raise ValueError(
                "Assessment с учебными целями "
                "может включать классы только "
                "одной параллели."
            )

    # =====================================================
    # STUDENT SNAPSHOT
    # =====================================================

    @staticmethod
    def _build_assessment_students(
            *,
            school_id: int,
            enrollments: list[
                SchoolStudentEnrollment
            ],
            group_by_class_id: dict[
                int,
                AssessmentGroup,
            ],
    ) -> list[AssessmentStudent]:
        students: list[AssessmentStudent] = []

        for enrollment in enrollments:
            group = group_by_class_id.get(
                enrollment.school_class_id
            )

            if group is None:
                raise ValueError(
                    "Для ученика не найдена "
                    "AssessmentGroup."
                )

            student = enrollment.student

            students.append(
                AssessmentStudent(
                    school_id=school_id,

                    assessment_group_id=group.id,
                    student_id=student.id,

                    student_name_snapshot=(
                        student.full_name
                    ),

                    participation_status=(
                        AssessmentParticipationStatus.ASSIGNED
                    ),
                )
            )

        return students

    # =====================================================
    # RESULT VALIDATION
    # =====================================================

    @staticmethod
    def _validate_result_payload(
            dto: ManualAssessmentSaveDTO,
    ) -> None:
        ids = [
            item.assessment_student_id
            for item in dto.results
        ]

        if len(ids) != len(set(ids)):
            raise ValueError(
                "Один участник Assessment "
                "передан несколько раз."
            )

    @staticmethod
    def _validate_non_completed_result(
            *,
            score: Decimal | None,
            objective_scores: tuple,
    ) -> None:
        """
        Для ABSENT / EXCUSED / NOT_COMPLETED
        никаких баллов быть не должно.
        """

        if score is not None:
            raise ValueError(
                "Балл можно указывать только "
                "для выполненной работы."
            )

        if objective_scores:
            raise ValueError(
                "Балл по учебным целям можно "
                "указывать только для выполненной работы."
            )

    @staticmethod
    def _validate_without_objectives_result(
            *,
            score: Decimal | None,
            objective_scores: tuple,
            max_score: Decimal,
    ) -> None:
        """
        Проверка COMPLETED результата
        без учебных целей.
        """

        if score is None:
            raise ValueError(
                "Для выполненной работы "
                "необходимо указать балл."
            )

        if score < 0:
            raise ValueError(
                "Балл не может быть отрицательным."
            )

        if score > max_score:
            raise ValueError(
                "Балл не может превышать "
                "максимальный балл Assessment."
            )

        if objective_scores:
            raise ValueError(
                "Assessment без учебных целей "
                "не должен содержать objective_scores."
            )

    @staticmethod
    def _validate_objective_result(
            *,
            direct_score: Decimal | None,
            objective_scores: tuple,
            objective_by_id: dict,
            expected_objective_ids: set[int],
    ) -> None:
        """
        Проверка результата работы по учебным целям.

        Общий score клиент не передаёт.

        Для каждой AssessmentObjective должна быть
        ровно одна запись objective_score.
        """

        if direct_score is not None:
            raise ValueError(
                "Для Assessment с учебными целями "
                "общий балл не передаётся. "
                "Он рассчитывается автоматически."
            )

        if not objective_scores:
            raise ValueError(
                "Для выполненной работы необходимо "
                "указать баллы по учебным целям."
            )

        submitted_ids = [
            item.assessment_objective_id
            for item in objective_scores
        ]

        # -----------------------------------------------------
        # DUPLICATES
        # -----------------------------------------------------

        if (
                len(submitted_ids)
                != len(set(submitted_ids))
        ):
            raise ValueError(
                "Одна учебная цель передана "
                "несколько раз."
            )

        submitted_id_set = set(
            submitted_ids
        )

        # -----------------------------------------------------
        # EXACT OBJECTIVE SET
        # -----------------------------------------------------

        if submitted_id_set != expected_objective_ids:
            raise ValueError(
                "Переданные учебные цели "
                "не соответствуют структуре Assessment."
            )

        # -----------------------------------------------------
        # SCORES
        # -----------------------------------------------------

        for item in objective_scores:

            objective = objective_by_id.get(
                item.assessment_objective_id
            )

            if objective is None:
                raise ValueError(
                    "Учебная цель не относится "
                    "к выбранному Assessment."
                )

            max_score = cast(
                Decimal,
                objective.max_score,
            )

            if item.score < 0:
                raise ValueError(
                    "Балл по учебной цели "
                    "не может быть отрицательным."
                )

            if item.score > max_score:
                raise ValueError(
                    f"Балл по учебной цели "
                    f"{objective.code_snapshot} "
                    f"не может превышать "
                    f"{max_score}."
                )

    # =====================================================
    # STATE VALIDATION
    # =====================================================

    @staticmethod
    def _validate_manual_assessment_state(
            assessment: Assessment,
    ) -> None:
        if (
                assessment.input_mode
                != AssessmentInputMode.MANUAL
        ):
            raise ValueError(
                "Assessment не относится "
                "к ручному режиму."
            )

        if assessment.status in {
            AssessmentStatus.COMPLETED,
            AssessmentStatus.ARCHIVED,
        }:
            raise ValueError(
                "Редактирование завершённого "
                "Assessment запрещено."
            )
