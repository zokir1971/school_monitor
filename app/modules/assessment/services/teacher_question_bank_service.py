# app/modules/assessment/services/teacher_question_bank_service.py

from __future__ import annotations

from dataclasses import replace

from app.modules.assessment.helpers.manual_review_criteria import validate_manual_criteria

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.services.question_bank_media_service import validate_media_segment

from app.modules.assessment.enums import (
    QuestionBankItemStatus,
)
from app.modules.assessment.repositories.teacher_question_bank_repo import (
    TeacherQuestionBankRepo,
    TeacherQuestionBankRow,
    TeacherQuestionBankDetail,
    TeacherQuestionBankTeachingScopeRow,
    TeacherQuestionBankLearningObjectiveRow,
    TeacherQuestionBankObjectiveValidationRow,
    TeacherQuestionBankCatalogRow, TeacherQuestionBankObjectiveRow,
)
from app.modules.assessment.schemas.teacher_question_bank_dto import (
    TeacherQuestionBankCountersDTO,
    TeacherQuestionBankItemDTO,
    TeacherQuestionBankPageDTO,
    TeacherQuestionBankDetailDTO,
    TeacherQuestionBankObjectiveDTO,
    TeacherQuestionBankReviewDTO,
    TeacherQuestionBankCreateContextDTO,
    TeacherQuestionBankTeachingScopeDTO,
    TeacherQuestionBankLearningObjectiveDTO,
    TeacherQuestionBankCreatedDraftDTO,
    TeacherQuestionBankCreateDraftDTO,
    TeacherQuestionBankCatalogFilterDTO,
    TeacherQuestionBankCatalogPageDTO,
    TeacherQuestionBankCatalogItemDTO, TeacherQuestionBankEditContextDTO, TeacherQuestionBankUpdateDraftDTO,
)
from app.modules.assessment.services.assessment_question_validation_service import (
    AssessmentQuestionValidationService,
)
from app.modules.assessment.services.question_bank_service import QuestionBankService


class TeacherQuestionBankService:
    """
    Read service Question Bank
    для рабочего кабинета учителя.
    """

    # =====================================================
    # PAGE
    # =====================================================

    @classmethod
    async def get_page(
            cls,
            db: AsyncSession,
            *,
            user_id: int,
            status: QuestionBankItemStatus | None = None,
            filters: dict | None = None,
    ) -> TeacherQuestionBankPageDTO:
        """
        Подготавливает данные страницы
        собственных заданий учителя.

        Считает статусы по уже загруженному списку.
        Дополнительных SQL-запросов не выполняет.
        """
        cls._validate_user_id(
            user_id
        )

        all_rows = await TeacherQuestionBankRepo.get_many_for_teacher(
            db,
            created_by_user_id=user_id,
            filters=filters,
        )

        counters = cls._build_counters(
            all_rows
        )

        if status is None:
            visible_rows = all_rows
        else:
            visible_rows = [
                row
                for row in all_rows
                if row.status == status
            ]

        return TeacherQuestionBankPageDTO(
            items=[
                cls._build_item_dto(row)
                for row in visible_rows
            ],
            counters=counters,
            selected_status=status,
        )

    # =========================================================
    # DETAIL
    # =========================================================

    @classmethod
    async def get_detail(
            cls,
            db: AsyncSession,
            *,
            user_id: int,
            item_id: int,
    ) -> TeacherQuestionBankDetailDTO | None:
        """
        Получает полную карточку собственного
        QuestionBankItem учителя.

        Ownership проверяется repository непосредственно
        в SQL через created_by_user_id.

        Если задание не существует либо принадлежит
        другому пользователю, возвращается None.
        """

        cls._validate_user_id(
            user_id
        )

        cls._validate_item_id(
            item_id
        )

        detail = await TeacherQuestionBankRepo.get_detail_for_teacher(
            db,
            item_id=item_id,
            created_by_user_id=user_id,
        )

        if detail is None:
            return None

        return cls._build_detail_dto(
            detail
        )

    # =========================================================
    # CREATE CONTEXT
    # =========================================================

    @classmethod
    async def get_create_context(
            cls,
            db: AsyncSession,
            *,
            staff_member_id: int,
    ) -> TeacherQuestionBankCreateContextDTO:
        """
        Формирует контекст страницы создания задания.

        Предметы и классы определяются только
        активными назначениями текущего учителя.
        """

        cls._validate_staff_member_id(
            staff_member_id
        )

        rows = await TeacherQuestionBankRepo.list_teaching_scope(
            db,
            staff_member_id=staff_member_id,
        )

        return TeacherQuestionBankCreateContextDTO(
            teaching_scope=[
                cls._build_teaching_scope_dto(row)
                for row in rows
            ],
        )

    @classmethod
    async def get_learning_objectives(
            cls,
            db: AsyncSession,
            *,
            staff_member_id: int,
            subject_id: int,
            grade_level: int,
            quarter: int,
            education_track: str | None = None,
    ) -> list[TeacherQuestionBankLearningObjectiveDTO]:
        """
        Возвращает активные учебные цели
        разрешённого учителю предмета,
        класса и четверти.
        """

        cls._validate_staff_member_id(
            staff_member_id
        )
        cls._validate_subject_id(
            subject_id
        )
        cls._validate_grade_level(
            grade_level
        )
        cls._validate_quarter(
            quarter
        )

        allowed = await TeacherQuestionBankRepo.has_teaching_scope(
            db,
            staff_member_id=staff_member_id,
            subject_id=subject_id,
            grade_level=grade_level,
        )

        if not allowed:
            return []

        rows = await TeacherQuestionBankRepo.list_learning_objectives(
            db,
            subject_id=subject_id,
            grade_level=grade_level,
            quarter=quarter,
            education_track=education_track,
        )

        return [
            cls._build_learning_objective_dto(row)
            for row in rows
        ]

    # =========================================================
    # EDIT CONTEXT
    # =========================================================

    @classmethod
    async def get_edit_context(
            cls,
            db: AsyncSession,
            *,
            user_id: int,
            staff_member_id: int,
            item_id: int,
    ) -> TeacherQuestionBankEditContextDTO:
        """
        Формирует контекст страницы редактирования
        собственного задания учителя.

        Редактирование разрешено только для:
            - DRAFT;
            - REJECTED.

        Возвращает:
            - полную карточку задания;
            - teaching scope текущего учителя;
            - LearningObjective текущего
              предмета / класса / четверти.
        """

        cls._validate_user_id(
            user_id
        )

        cls._validate_staff_member_id(
            staff_member_id
        )

        cls._validate_item_id(
            item_id
        )

        # =====================================================
        # 1. OWNERSHIP + DETAIL
        # =====================================================

        detail = await TeacherQuestionBankRepo.get_detail_for_teacher(
            db,
            item_id=item_id,
            created_by_user_id=user_id,
        )

        if detail is None:
            raise ValueError(
                "Задание не найдено или недоступно."
            )

        # =====================================================
        # 2. EDITABLE STATUS
        # =====================================================

        cls._validate_editable_status(
            detail.status
        )

        # =====================================================
        # 3. DETAIL DTO
        # =====================================================

        item_dto = cls._build_detail_dto(
            detail
        )

        # =====================================================
        # 4. TEACHING SCOPE
        # =====================================================

        scope_rows = (
            await TeacherQuestionBankRepo.list_teaching_scope(
                db,
                staff_member_id=staff_member_id,
            )
        )

        teaching_scope = [
            cls._build_teaching_scope_dto(row)
            for row in scope_rows
        ]

        # =====================================================
        # 5. CURRENT TEACHING SCOPE
        # =====================================================

        allowed = await TeacherQuestionBankRepo.has_teaching_scope(
            db,
            staff_member_id=staff_member_id,
            subject_id=item_dto.subject_id,
            grade_level=item_dto.grade_level,
        )

        if not allowed:
            raise ValueError(
                "Предмет и класс задания больше не входят "
                "в teaching scope текущего учителя."
            )

        # =====================================================
        # 6. LEARNING OBJECTIVES
        # =====================================================

        objective_rows = (
            await TeacherQuestionBankRepo.list_learning_objectives(
                db,
                subject_id=item_dto.subject_id,
                grade_level=item_dto.grade_level,
                quarter=item_dto.quarter,
            )
        )

        learning_objectives = [
            cls._build_learning_objective_dto(row)
            for row in objective_rows
        ]

        # =====================================================
        # 7. RESULT
        # =====================================================

        return TeacherQuestionBankEditContextDTO(
            item=item_dto,
            teaching_scope=teaching_scope,
            learning_objectives=learning_objectives,
        )

    # =====================================================
    # COUNTERS
    # =====================================================

    @staticmethod
    def _build_counters(
            rows: list[TeacherQuestionBankRow],
    ) -> TeacherQuestionBankCountersDTO:
        """
        Пока получает полный собственный список
        одним дополнительным запросом и считает
        статусы в памяти.

        N+1 здесь нет:
            1 запрос — текущий список;
            1 запрос — данные для counters.

        Позже при необходимости можно заменить
        специализированным GROUP BY запросом.
        """
        counters = {
            QuestionBankItemStatus.DRAFT: 0,
            QuestionBankItemStatus.REVIEW: 0,
            QuestionBankItemStatus.READY: 0,
            QuestionBankItemStatus.REJECTED: 0,
            QuestionBankItemStatus.ARCHIVED: 0,
        }

        for row in rows:
            if row.status in counters:
                counters[row.status] += 1

        return TeacherQuestionBankCountersDTO(
            total=len(rows),
            draft=counters[
                QuestionBankItemStatus.DRAFT
            ],
            review=counters[
                QuestionBankItemStatus.REVIEW
            ],
            ready=counters[
                QuestionBankItemStatus.READY
            ],
            rejected=counters[
                QuestionBankItemStatus.REJECTED
            ],
            archived=counters[
                QuestionBankItemStatus.ARCHIVED
            ],
        )

    # =====================================================
    # MAPPERS
    # =====================================================

    @staticmethod
    def _build_item_dto(
            row: TeacherQuestionBankRow,
    ) -> TeacherQuestionBankItemDTO:
        return TeacherQuestionBankItemDTO(
            item_id=row.item_id,

            subject_id=row.subject_id,
            subject_name=row.subject_name,

            grade_level=row.grade_level,

            question_type=row.question_type,
            difficulty=row.difficulty,
            language=row.language,

            status=row.status,
            origin=row.origin,

            title=row.title,
            text=row.text,

            objective_count=row.objective_count,

            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @classmethod
    def _build_detail_dto(
            cls,
            detail: TeacherQuestionBankDetail,
    ) -> TeacherQuestionBankDetailDTO:
        quarter = cls._resolve_item_quarter(
            detail.objectives
        )

        return TeacherQuestionBankDetailDTO(
            item_id=detail.item_id,

            subject_id=detail.subject_id,
            subject_name=detail.subject_name,

            grade_level=detail.grade_level,
            quarter=quarter,

            question_type=detail.question_type,
            difficulty=detail.difficulty,
            language=detail.language,

            status=detail.status,
            origin=detail.origin,

            title=detail.title,

            text=detail.text,
            text_segments=[
                dict(segment)
                for segment in detail.text_segments
            ],

            instruction=detail.instruction,

            content=dict(detail.content),
            answer_key=dict(detail.answer_key),
            grading_settings=dict(
                detail.grading_settings
            ),

            max_score=detail.max_score,

            explanation=detail.explanation,
            author_comment=detail.author_comment,

            created_at=detail.created_at,
            updated_at=detail.updated_at,

            objectives=[
                cls._build_objective_dto(objective)
                for objective in detail.objectives
            ],

            reviews=[
                TeacherQuestionBankReviewDTO(
                    review_id=review.review_id,
                    reviewer_user_id=(
                        review.reviewer_user_id
                    ),
                    reviewer_name=review.reviewer_name,
                    decision=review.decision,
                    comment=review.comment,
                    created_at=review.created_at,
                )
                for review in detail.reviews
            ],
        )

    @staticmethod
    def _build_teaching_scope_dto(
            row: TeacherQuestionBankTeachingScopeRow,
    ) -> TeacherQuestionBankTeachingScopeDTO:
        return TeacherQuestionBankTeachingScopeDTO(
            subject_id=row.subject_id,
            subject_code=row.subject_code,

            subject_name_kz=row.subject_name_kz,
            subject_name_ru=row.subject_name_ru,

            grade_level=row.grade_level,
        )

    @staticmethod
    def _build_learning_objective_dto(
            row: TeacherQuestionBankLearningObjectiveRow,
    ) -> TeacherQuestionBankLearningObjectiveDTO:
        return TeacherQuestionBankLearningObjectiveDTO(
            learning_objective_id=(
                row.learning_objective_id
            ),
            quarter=row.quarter,
            code=row.code,
            title_kz=row.title_kz,
            title_ru=row.title_ru,
            title_segments_kz=tuple(getattr(row, "title_segments_kz", ()) or ()),
            title_segments_ru=tuple(getattr(row, "title_segments_ru", ()) or ()),
        )

    @staticmethod
    def _group_objectives_by_item_id(
            rows: list[TeacherQuestionBankObjectiveRow],
    ) -> dict[int, list[TeacherQuestionBankObjectiveRow]]:
        grouped: dict[
            int,
            list[TeacherQuestionBankObjectiveRow],
        ] = {}

        for row in rows:
            grouped.setdefault(
                row.question_bank_item_id,
                [],
            ).append(row)

        return grouped

    @classmethod
    def _build_catalog_item_dto(
            cls,
            row: TeacherQuestionBankCatalogRow,
            *,
            user_id: int,
            objectives: list[
                TeacherQuestionBankObjectiveRow
            ],
    ) -> TeacherQuestionBankCatalogItemDTO:
        """
        Преобразует read-model общего банка
        в DTO карточки каталога.

        is_own не влияет на видимость задания.
        Он только сообщает UI, является ли
        текущий пользователь автором.
        """

        quarter = cls._resolve_item_quarter(
            objectives
        )

        return TeacherQuestionBankCatalogItemDTO(
            item_id=row.item_id,

            subject_id=row.subject_id,
            subject_name=row.subject_name,

            grade_level=row.grade_level,
            quarter=quarter,

            objectives=[
                cls._build_objective_dto(objective)
                for objective in objectives
            ],

            question_type=row.question_type,
            difficulty=row.difficulty,
            language=row.language,

            status=row.status,
            origin=row.origin,

            title=row.title,

            text=row.text,

            text_segments=[
                dict(segment)
                for segment in row.text_segments
            ],

            instruction=row.instruction,

            content=dict(row.content),
            answer_key=dict(row.answer_key),
            grading_settings=dict(row.grading_settings),
            explanation=row.explanation,

            max_score=row.max_score,

            created_by_user_id=(
                row.created_by_user_id
            ),
            author_name=row.author_name,

            is_own=(
                    row.created_by_user_id
                    == user_id
            ),

            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    # =====================================================
    # VALIDATION
    # =====================================================

    @staticmethod
    def _validate_user_id(
            user_id: int,
    ) -> None:
        if not isinstance(
                user_id,
                int,
        ):
            raise ValueError(
                "user_id must be int."
            )

        if user_id <= 0:
            raise ValueError(
                "user_id must be greater than 0."
            )

    @staticmethod
    def _validate_item_id(
            item_id: int,
    ) -> None:
        if not isinstance(
                item_id,
                int,
        ):
            raise ValueError(
                "item_id must be int."
            )

        if item_id <= 0:
            raise ValueError(
                "item_id must be greater than 0."
            )

    @staticmethod
    def _validate_staff_member_id(
            staff_member_id: int,
    ) -> None:
        if not isinstance(
                staff_member_id,
                int,
        ):
            raise ValueError(
                "staff_member_id must be int."
            )

        if staff_member_id <= 0:
            raise ValueError(
                "staff_member_id must be greater than 0."
            )

    @staticmethod
    def _validate_subject_id(
            subject_id: int,
    ) -> None:
        if not isinstance(
                subject_id,
                int,
        ):
            raise ValueError(
                "subject_id must be int."
            )

        if subject_id <= 0:
            raise ValueError(
                "subject_id must be greater than 0."
            )

    @staticmethod
    def _validate_grade_level(
            grade_level: int,
    ) -> None:
        if not isinstance(
                grade_level,
                int,
        ):
            raise ValueError(
                "grade_level must be int."
            )

        if not 1 <= grade_level <= 12:
            raise ValueError(
                "grade_level must be between 1 and 12."
            )

    @staticmethod
    def _validate_quarter(
            quarter: int,
    ) -> None:
        if not isinstance(quarter, int):
            raise ValueError(
                "quarter must be int."
            )

        if not 1 <= quarter <= 4:
            raise ValueError(
                "quarter must be between 1 and 4."
            )

    @staticmethod
    def _validate_objective_id(
            objective_id: int,
    ) -> None:
        if not isinstance(
                objective_id,
                int,
        ):
            raise ValueError(
                "objective_id must be int."
            )

        if objective_id <= 0:
            raise ValueError(
                "objective_id must be greater than 0."
            )

    @staticmethod
    def _validate_editable_status(
            status: QuestionBankItemStatus,
    ) -> None:
        """
        Проверяет возможность редактирования задания.

        Допустимые состояния:
            DRAFT
            REJECTED
        """

        if status not in {
            QuestionBankItemStatus.DRAFT,
            QuestionBankItemStatus.REJECTED,
        }:
            raise ValueError(
                "Редактирование задания доступно только "
                "в статусах DRAFT или REJECTED."
            )

    @classmethod
    async def create_draft(
            cls,
            db: AsyncSession,
            *,
            user_id: int,
            staff_member_id: int,
            data: TeacherQuestionBankCreateDraftDTO,
            commit: bool = True,
    ) -> TeacherQuestionBankCreatedDraftDTO:
        """
        Создаёт QuestionBankItem в статусе DRAFT
        от имени текущего учителя.

        Весь use-case выполняется в единой
        транзакционной границе.

        Проверяет:
        - user_id и staff_member_id;
        - teaching scope учителя;
        - subject / grade / quarter;
        - выбранные LearningObjective одним bulk SELECT;
        - принадлежность целей выбранному контексту;
        - технический контракт задания.

        При любой ошибке выполняется rollback.
        """

        try:
            # =================================================
            # 1. BASIC VALIDATION
            # =================================================

            cls._validate_user_id(
                user_id
            )

            cls._validate_staff_member_id(
                staff_member_id
            )

            cls._validate_subject_id(
                data.subject_id
            )

            cls._validate_grade_level(
                data.grade_level
            )

            cls._validate_quarter(
                data.quarter
            )

            objective_ids = (
                cls._normalize_objective_ids(
                    [data.objective_id]
                )
            )

            # =================================================
            # 2. TEACHING SCOPE
            # =================================================

            allowed = (
                await TeacherQuestionBankRepo.has_teaching_scope(
                    db,
                    staff_member_id=staff_member_id,
                    subject_id=data.subject_id,
                    grade_level=data.grade_level,
                )
            )

            if not allowed:
                raise ValueError(
                    "Выбранные предмет и класс "
                    "не входят в teaching scope учителя."
                )

            # =================================================
            # 3. LEARNING OBJECTIVES
            #    ONE BULK SELECT
            # =================================================

            objective_rows = (
                await TeacherQuestionBankRepo.list_objectives_for_validation(
                    db,
                    objective_ids=objective_ids,
                    quarter=data.quarter,
                )
            )

            cls._validate_selected_objectives(
                objective_ids=objective_ids,
                rows=objective_rows,
                subject_id=data.subject_id,
                grade_level=data.grade_level,
                quarter=data.quarter,
            )

            # =================================================
            # 4. TECHNICAL QUESTION CONTRACT
            # =================================================

            if data.question_type.value == "manual_review":
                validate_manual_criteria(
                    data.grading_settings.get("criteria"), max_score=data.max_score,
                )

            AssessmentQuestionValidationService.validate_authoring(
                question_type=data.question_type,
                content=data.content,
                answer_key=data.answer_key,
                grading_settings=data.grading_settings,
                max_score=data.max_score,
            )

            # =================================================
            # 5. CREATE AGGREGATE
            # =================================================

            item = (
                await TeacherQuestionBankRepo.create_draft(
                    db,
                    subject_id=data.subject_id,
                    grade_level=data.grade_level,

                    question_type=data.question_type,
                    difficulty=data.difficulty,
                    language=data.language,

                    title=cls._normalize_optional_text(
                        data.title
                    ),

                    text=cls._normalize_required_text(
                        data.text,
                        field_name="text",
                    ),

                    text_segments=cls._normalize_text_segments(
                        data.text_segments
                    ),

                    instruction=cls._normalize_optional_text(
                        data.instruction
                    ),
                    content=dict(
                        data.content
                    ),

                    answer_key=dict(
                        data.answer_key
                    ),

                    grading_settings=dict(
                        data.grading_settings
                    ),

                    max_score=data.max_score,

                    explanation=cls._normalize_optional_text(
                        data.explanation
                    ),

                    author_comment=cls._normalize_optional_text(
                        data.author_comment
                    ),

                    created_by_user_id=user_id,
                    objective_ids=objective_ids,
                    quarter=data.quarter,
                )
            )

            # =================================================
            # 6. COMMIT
            # =================================================

            if commit:
                await db.commit()
            else:
                await db.flush()

            return TeacherQuestionBankCreatedDraftDTO(
                item_id=item.id,
                status=item.status,
            )

        except Exception:
            await db.rollback()
            raise

    # =========================================================
    # UPDATE DRAFT
    # =========================================================

    @classmethod
    async def update_draft(
            cls,
            db: AsyncSession,
            *,
            user_id: int,
            staff_member_id: int,
            item_id: int,
            data: TeacherQuestionBankUpdateDraftDTO,
    ) -> TeacherQuestionBankCreatedDraftDTO:
        """
        Обновляет собственное задание учителя.

        Допустимые исходные статусы:
            DRAFT
            REJECTED

        После успешного сохранения:
            DRAFT    -> DRAFT
            REJECTED -> DRAFT

        Выполняет:
            - ownership validation;
            - lifecycle validation;
            - teaching scope validation;
            - LearningObjective validation;
            - technical question validation;
            - обновление агрегата;
            - commit.

        При ошибке выполняется rollback.
        """

        try:
            # =================================================
            # 1. BASIC VALIDATION
            # =================================================

            cls._validate_user_id(
                user_id
            )

            cls._validate_staff_member_id(
                staff_member_id
            )

            cls._validate_item_id(
                item_id
            )

            cls._validate_subject_id(
                data.subject_id
            )

            cls._validate_grade_level(
                data.grade_level
            )

            cls._validate_quarter(
                data.quarter
            )

            objective_ids = cls._normalize_objective_ids(
                [data.objective_id]
            )

            # =================================================
            # 2. OWNERSHIP
            # =================================================

            item = await TeacherQuestionBankRepo.get_item_for_teacher(
                db,
                item_id=item_id,
                created_by_user_id=user_id,
            )

            if item is None:
                raise ValueError(
                    "Задание не найдено или недоступно."
                )

            # =================================================
            # 3. EDITABLE STATUS
            # =================================================

            cls._validate_editable_status(
                item.status
            )

            # =================================================
            # 4. TEACHING SCOPE
            # =================================================

            allowed = await TeacherQuestionBankRepo.has_teaching_scope(
                db,
                staff_member_id=staff_member_id,
                subject_id=data.subject_id,
                grade_level=data.grade_level,
            )

            if not allowed:
                raise ValueError(
                    "Выбранные предмет и класс "
                    "не входят в teaching scope учителя."
                )

            # =================================================
            # 5. LEARNING OBJECTIVE
            # =================================================

            objective_rows = (
                await TeacherQuestionBankRepo.list_objectives_for_validation(
                    db,
                    objective_ids=objective_ids,
                    quarter=data.quarter,
                )
            )

            cls._validate_selected_objectives(
                objective_ids=objective_ids,
                rows=objective_rows,
                subject_id=data.subject_id,
                grade_level=data.grade_level,
                quarter=data.quarter,
            )

            # =================================================
            # 6. TECHNICAL QUESTION CONTRACT
            # =================================================

            if data.question_type.value == "manual_review":
                validate_manual_criteria(
                    data.grading_settings.get("criteria"), max_score=data.max_score,
                )

            AssessmentQuestionValidationService.validate_authoring(
                question_type=data.question_type,
                content=data.content,
                answer_key=data.answer_key,
                grading_settings=data.grading_settings,
                max_score=data.max_score,
            )

            # =================================================
            # 7. NORMALIZE DATA
            # =================================================

            title = cls._normalize_optional_text(
                data.title
            )

            text = cls._normalize_required_text(
                data.text,
                field_name="text",
            )

            text_segments = cls._normalize_text_segments(
                data.text_segments
            )

            instruction = cls._normalize_optional_text(
                data.instruction
            )

            explanation = cls._normalize_optional_text(
                data.explanation
            )

            author_comment = cls._normalize_optional_text(
                data.author_comment
            )

            # =================================================
            # 8. UPDATE AGGREGATE
            # =================================================

            item = await TeacherQuestionBankRepo.update_draft(
                db,
                item=item,

                subject_id=data.subject_id,
                grade_level=data.grade_level,

                question_type=data.question_type,
                difficulty=data.difficulty,
                language=data.language,

                title=title,

                text=text,
                text_segments=text_segments,

                instruction=instruction,

                content=dict(
                    data.content
                ),

                answer_key=dict(
                    data.answer_key
                ),

                grading_settings=dict(
                    data.grading_settings
                ),

                max_score=data.max_score,

                explanation=explanation,
                author_comment=author_comment,

                objective_ids=objective_ids,
                quarter=data.quarter,
            )

            # =================================================
            # 9. LIFECYCLE
            #    REJECTED -> DRAFT
            # =================================================

            if item.status == QuestionBankItemStatus.REJECTED:
                item.status = QuestionBankItemStatus.DRAFT

            # =================================================
            # 10. COMMIT
            # =================================================

            await db.commit()

            return TeacherQuestionBankCreatedDraftDTO(
                item_id=item.id,
                status=item.status,
            )

        except Exception:
            await db.rollback()
            raise

    @staticmethod
    def _validate_selected_objectives(
            *,
            objective_ids: list[int],
            rows: list[
                TeacherQuestionBankObjectiveValidationRow
            ],
            subject_id: int,
            grade_level: int,
            quarter: int,
    ) -> None:
        """
        Проверяет результат одного bulk SELECT.

        Дополнительных запросов к БД здесь нет.
        """

        rows_by_id = {
            row.learning_objective_id: row
            for row in rows
        }

        missing_ids = [
            objective_id
            for objective_id in objective_ids
            if objective_id not in rows_by_id
        ]

        if missing_ids:
            raise ValueError(
                "LearningObjective не найдены: "
                + ", ".join(
                    str(value)
                    for value in missing_ids
                )
            )

        tracks = {getattr(rows_by_id[key], "education_track", "") for key in objective_ids}
        if len(tracks) > 1:
            raise ValueError("Нельзя объединять цели разных направлений обучения в одном задании.")
        for objective_id in objective_ids:
            row = rows_by_id[objective_id]

            if not row.is_active:
                raise ValueError(
                    f"LearningObjective "
                    f"{objective_id} неактивна."
                )

            if row.subject_id != subject_id:
                raise ValueError(
                    f"LearningObjective "
                    f"{objective_id} относится "
                    f"к другому предмету."
                )

            if row.grade_level != grade_level:
                raise ValueError(
                    f"LearningObjective "
                    f"{objective_id} относится "
                    f"к другому классу."
                )

            if row.quarter != quarter:
                raise ValueError(
                    f"LearningObjective "
                    f"{objective_id} относится "
                    f"к другой четверти."
                )

    @staticmethod
    def _build_objective_dto(
            row: TeacherQuestionBankObjectiveRow,
    ) -> TeacherQuestionBankObjectiveDTO:
        return TeacherQuestionBankObjectiveDTO(
            learning_objective_id=(
                row.learning_objective_id
            ),
            quarter=row.quarter,
            code=row.code,
            title_kz=row.title_kz,
            title_ru=row.title_ru,
            order_no=row.order_no,
        )

    @classmethod
    def _resolve_item_quarter(
            cls,
            objectives: list[TeacherQuestionBankObjectiveRow],
    ) -> int:
        if not objectives:
            raise ValueError(
                "QuestionBankItem не содержит учебных целей."
            )

        quarters = {
            objective.quarter
            for objective in objectives
        }

        if len(quarters) != 1:
            raise ValueError(
                "Учебные цели QuestionBankItem относятся "
                "к разным четвертям."
            )

        quarter = next(iter(quarters))

        cls._validate_quarter(
            quarter
        )

        return quarter

    @staticmethod
    def _normalize_objective_ids(
            objective_ids: list[int],
    ) -> list[int]:
        if not isinstance(objective_ids, list):
            raise ValueError(
                "objective_ids must be list."
            )

        if not objective_ids:
            raise ValueError(
                "Необходимо выбрать хотя бы "
                "одну учебную цель."
            )

        normalized: list[int] = []

        seen: set[int] = set()

        for objective_id in objective_ids:
            if not isinstance(objective_id, int):
                raise ValueError(
                    "objective_ids must contain integers."
                )

            if objective_id <= 0:
                raise ValueError(
                    "objective_ids must contain "
                    "positive integers."
                )

            if objective_id in seen:
                continue

            seen.add(objective_id)
            normalized.append(objective_id)

        return normalized

    @staticmethod
    def _normalize_required_text(
            value: str,
            *,
            field_name: str,
    ) -> str:
        if not isinstance(value, str):
            raise ValueError(
                f"{field_name} must be str."
            )

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                f"{field_name} must not be empty."
            )

        return normalized

    @staticmethod
    def _normalize_text_segments(
            segments: list[dict],
    ) -> list[dict]:
        if not isinstance(
                segments,
                list,
        ):
            raise ValueError(
                "text_segments must be list."
            )

        if not segments:
            raise ValueError(
                "text_segments must not be empty."
            )

        normalized: list[dict] = []

        for index, segment in enumerate(
                segments
        ):
            if not isinstance(
                    segment,
                    dict,
            ):
                raise ValueError(
                    f"text_segments[{index}] "
                    "must be dict."
                )

            segment_type = segment.get(
                "type"
            )

            if segment_type == "image":
                try:
                    validate_media_segment(segment)
                except ValueError as exc:
                    raise ValueError(
                        f"text_segments[{index}]: {exc}"
                    ) from exc
                normalized.append(
                    {
                        "type": "image",
                        "object_key": segment["object_key"],
                        "alt": segment.get("alt", ""),
                    }
                )
                continue

            if segment_type not in {
                "text",
                "latex",
            }:
                raise ValueError(
                    f"text_segments[{index}].type "
                    "must be 'text', 'latex' or 'image'."
                )

            value = segment.get(
                "text"
            )

            if not isinstance(
                    value,
                    str,
            ):
                raise ValueError(
                    f"text_segments[{index}].text "
                    "must be str."
                )

            if not value:
                continue

            normalized.append(
                {
                    "type": segment_type,
                    "text": value,
                }
            )

        if not normalized:
            raise ValueError(
                "text_segments must contain "
                "non-empty content."
            )

        return normalized

    @staticmethod
    def _normalize_optional_text(
            value: str | None,
    ) -> str | None:
        if value is None:
            return None

        if not isinstance(value, str):
            raise ValueError(
                "Optional text value must be str or None."
            )

        normalized = value.strip()

        return normalized or None

    # =========================================================
    # QUESTION BANK CATALOG
    # =========================================================

    @classmethod
    async def get_catalog_page(
            cls,
            db: AsyncSession,
            *,
            user_id: int,
            staff_member_id: int | None,
            shared_ready: bool = False,
            education_track: str | None = None,
            offset: int = 0,
            subject_id: int | None = None,
            grade_level: int | None = None,
            quarter: int | None = None,
            objective_id: int | None = None,
    ) -> TeacherQuestionBankCatalogPageDTO:
        """READY catalog: subject/class context, optional track/quarter/objective.

        shared_ready selects the shared read scope, without author/teaching filters.
        Fetch one lookahead row and return 20 cards; objective links are bulk-loaded
        only for visible cards. No total COUNT or per-card database queries.
        """

        # =================================================
        # 1. BASIC VALIDATION
        # =================================================

        if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 1_000_000 or offset % 20:
            raise ValueError('Некорректная страница / Бет нөмірі дұрыс емес.')
        cls._validate_user_id(
            user_id
        )

        if not shared_ready:
            cls._validate_staff_member_id(staff_member_id)

        # =================================================
        # 2. TEACHING SCOPE
        # =================================================

        if shared_ready:
            scope_rows = await TeacherQuestionBankRepo.list_ready_catalog_scope(db)
        else:
            scope_rows = await TeacherQuestionBankRepo.list_teaching_scope(db, staff_member_id=staff_member_id)

        teaching_scope = [
            cls._build_teaching_scope_dto(row)
            for row in scope_rows
        ]

        # =================================================
        # 3. EMPTY / INCOMPLETE FILTER
        # =================================================

        filters = TeacherQuestionBankCatalogFilterDTO(
            subject_id=subject_id,
            grade_level=grade_level,
            quarter=quarter,
            objective_id=objective_id,
        )

        if (
                subject_id is None
                or grade_level is None
        ):
            return TeacherQuestionBankCatalogPageDTO(
                teaching_scope=teaching_scope,
                learning_objectives=[],
                filters=filters,
                items=[],
            )

        # =================================================
        # 4. VALIDATE SUBJECT + GRADE
        # =================================================

        cls._validate_subject_id(
            subject_id
        )

        cls._validate_grade_level(
            grade_level
        )

        if shared_ready:
            allowed = any(row.subject_id == subject_id and row.grade_level == grade_level for row in scope_rows)
        else:
            allowed = await TeacherQuestionBankRepo.has_teaching_scope(db,
                staff_member_id=staff_member_id, subject_id=subject_id, grade_level=grade_level)

        if not allowed:
            raise ValueError(
                "Выбранные предмет и класс "
                "недоступны в каталоге готовых заданий."
            )

        # =================================================
        # 5. QUARTER
        # =================================================

        from app.modules.assessment.helpers.ai_education_track import selected_track
        track = selected_track(grade_level, education_track) if education_track not in (None, '', 'all') else None
        if quarter is not None:
            cls._validate_quarter(quarter)

        # =================================================
        # 6. LEARNING OBJECTIVES
        # =================================================

        objective_rows = (
            await TeacherQuestionBankRepo.list_learning_objectives(
                db,
                subject_id=subject_id,
                grade_level=grade_level,
                quarter=quarter,
                education_track=track,
            )
        )

        learning_objectives = [
            cls._build_learning_objective_dto(row)
            for row in objective_rows
        ]

        # =================================================
        # 7. OBJECTIVE NOT SELECTED YET
        # =================================================

        if objective_id is not None:
            cls._validate_objective_id(objective_id)

        # =================================================
        # 8. OBJECTIVE MUST BELONG TO CURRENT CONTEXT
        # =================================================

        allowed_objective_ids = {
            row.learning_objective_id
            for row in objective_rows
        }

        if objective_id is not None and objective_id not in allowed_objective_ids:
            raise ValueError(
                "Выбранная учебная цель не относится "
                "к выбранному предмету, классу "
                "и четверти."
            )

        # =================================================
        # 9. GENERAL QUESTION BANK
        # =================================================

        item_rows = (
            await TeacherQuestionBankRepo.list_catalog_items(
                db,
                subject_id=subject_id,
                grade_level=grade_level,
                objective_id=objective_id,
                objective_ids=sorted(allowed_objective_ids),
                quarter=quarter,
                limit=21, offset=offset,
            )
        )

        has_next = len(item_rows) > 20
        item_rows = item_rows[:20]

        item_ids = [
            row.item_id
            for row in item_rows
        ]

        objective_rows_for_items = (
            await TeacherQuestionBankRepo.list_objectives_for_items(
                db,
                item_ids=item_ids,
            )
        )

        objectives_by_item_id = (
            cls._group_objectives_by_item_id(
                objective_rows_for_items
            )
        )

        items = [
            cls._build_catalog_item_dto(
                row,
                user_id=user_id,
                objectives=objectives_by_item_id.get(
                    row.item_id,
                    [],
                ),
            )
            for row in item_rows
        ]

        # Source language belongs to the item; translations are separate saved rows.
        variant_rows = await TeacherQuestionBankRepo.list_catalog_variant_languages(
            db, item_ids=item_ids,
        )
        languages_by_id = {item.item_id: {str(getattr(item.language, 'value', item.language))} for item in items}
        for variant in variant_rows:
            if variant.item_id in languages_by_id and variant.language in ('kk', 'ru'):
                languages_by_id[variant.item_id].add(variant.language)
        items = [replace(item, available_languages=tuple(sorted(languages_by_id[item.item_id]))) for item in items]

        # =================================================
        # 10. RESULT
        # =================================================

        return TeacherQuestionBankCatalogPageDTO(
            teaching_scope=teaching_scope,
            learning_objectives=learning_objectives,
            filters=filters,
            items=items,
            offset=offset, has_next=has_next,
        )

    # =========================================================
    # SUBMIT FOR REVIEW
    # =========================================================

    @classmethod
    async def submit_for_review(
            cls,
            db: AsyncSession,
            *,
            user_id: int,
            item_id: int,
    ) -> None:
        """
        Отправляет собственное задание учителя
        на Human Review.

        TeacherQuestionBankService отвечает за:
        - валидацию user_id / item_id;
        - ownership текущего учителя.

        Domain lifecycle:
            DRAFT -> REVIEW

        выполняет QuestionBankService.
        """

        # =========================================================
        # 1. BASIC VALIDATION
        # =========================================================

        cls._validate_user_id(
            user_id
        )

        cls._validate_item_id(
            item_id
        )

        # =========================================================
        # 2. OWNERSHIP
        # =========================================================

        detail = await TeacherQuestionBankRepo.get_detail_for_teacher(
            db,
            item_id=item_id,
            created_by_user_id=user_id,
        )

        if detail is None:
            raise ValueError(
                "Задание не найдено или недоступно."
            )

        # =========================================================
        # 3. DOMAIN ACTION: DRAFT -> REVIEW
        # =========================================================

        await QuestionBankService.submit_for_review(
            db,
            item_id=item_id,
        )
