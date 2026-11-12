# app/modules/assessment/services/question_bank_expert_service.py

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.models import QuestionBankItem
from app.modules.assessment.models_question_bank_experts import (
    QuestionBankExpert, QuestionBankExpertSpecialty,
)
from app.modules.assessment.repositories.question_bank_expert_repo import (
    QuestionBankExpertRepo,
)
from app.modules.assessment.repositories.teacher_question_bank_repo import TeacherQuestionBankRepo, \
    TeacherQuestionReviewRow, TeacherQuestionBankObjectiveRow
from app.modules.assessment.schemas.question_bank_expert_schemas import (
    QuestionBankExpertCreateDTO,
    QuestionBankExpertDetailDTO,
    QuestionBankExpertListItemDTO,
    QuestionBankExpertPageDTO,
    QuestionBankExpertSchoolDTO,
    QuestionBankExpertSubjectDTO,
    QuestionBankExpertUpdateDTO,
    QuestionBankExpertFormOptionsDTO,
    QuestionBankExpertDistrictDTO,
)
from app.modules.assessment.schemas.question_bank_review_dto import QuestionBankReviewCreateResult
from app.modules.assessment.schemas.teacher_question_bank_dto import TeacherQuestionReviewPageDTO, \
    TeacherQuestionReviewItemDTO, TeacherQuestionBankObjectiveDTO
from app.modules.assessment.services.question_bank_service import QuestionBankService


class QuestionBankExpertError(ValueError):
    """
    Ожидаемая бизнес-ошибка экспертного реестра.
    """


class QuestionBankExpertNotFoundError(QuestionBankExpertError):
    pass


class QuestionBankExpertService:

    @staticmethod
    async def specialty_options(db):
        result = await db.execute(select(
            QuestionBankExpertSpecialty.id, QuestionBankExpertSpecialty.name_ru, QuestionBankExpertSpecialty.name_kz,
        ).where(QuestionBankExpertSpecialty.is_active.is_(True)).order_by(QuestionBankExpertSpecialty.name_ru))
        return [dict(id=row.id, name=row.name_ru, name_ru=row.name_ru, name_kz=row.name_kz) for row in result]

    @staticmethod
    async def require_specialty(db, specialty_id):
        if not specialty_id or not await db.scalar(select(QuestionBankExpertSpecialty.id).where(
                QuestionBankExpertSpecialty.id == specialty_id,
                QuestionBankExpertSpecialty.is_active.is_(True),
        )):
            raise QuestionBankExpertError("Выберите действующую специальность эксперта.")

    # ========================================================
    # NORMALIZATION
    # ========================================================

    @staticmethod
    def _normalize_required_text(
            value: str,
            *,
            field_name: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise QuestionBankExpertError(
                f"{field_name} міндетті."
            )

        return value

    @staticmethod
    def _normalize_optional_text(
            value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @staticmethod
    def _normalize_iin(
            value: str,
    ) -> str:
        value = value.strip()

        if len(value) != 12 or not value.isdigit():
            raise QuestionBankExpertError(
                "ЖСН 12 цифрдан тұруы тиіс."
            )

        return value

    # ========================================================
    # VALIDATION
    # ========================================================

    @staticmethod
    def _validate_id(
            value: int,
            *,
            field_name: str,
    ) -> None:
        if value <= 0:
            raise QuestionBankExpertError(
                f"{field_name} дұрыс көрсетілмеген."
            )

    @classmethod
    def _validate_region_id(
            cls,
            region_id: int,
    ) -> None:
        cls._validate_id(
            region_id,
            field_name="Өңір",
        )

    @classmethod
    def _validate_user_id(
            cls,
            user_id: int,
    ) -> None:
        cls._validate_id(
            user_id,
            field_name="Пайдаланушы",
        )

    @staticmethod
    def _validate_experience(
            value: int | None,
    ) -> None:
        if value is not None and value < 0:
            raise QuestionBankExpertError(
                "Педагогикалық өтіл теріс болмауы тиіс."
            )

    # ========================================================
    # REGIONAL SECURITY
    # ========================================================

    @classmethod
    async def _require_school_in_region(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            region_id: int,
    ) -> None:
        cls._validate_id(
            school_id,
            field_name="Мектеп",
        )

        belongs = (
            await QuestionBankExpertRepo
            .school_belongs_to_region(
                db,
                school_id=school_id,
                region_id=region_id,
            )
        )

        if not belongs:
            raise QuestionBankExpertError(
                "Таңдалған білім беру ұйымы "
                "осы өңірге жатпайды."
            )

    # ========================================================
    # PAGE
    # ========================================================

    @classmethod
    async def get_page(
            cls,
            db: AsyncSession,
            *,
            region_id: int,
            active_only: bool | None = None,
            district_id: int | None = None,
            subject_id: int | None = None,
    ) -> QuestionBankExpertPageDTO:

        cls._validate_region_id(region_id)

        if district_id is not None:
            cls._validate_id(
                district_id,
                field_name="Аудан",
            )

        if subject_id is not None:
            cls._validate_id(
                subject_id,
                field_name="Пән",
            )

        experts = await QuestionBankExpertRepo.list_for_region(
            db,
            region_id=region_id,
            active_only=active_only,
            district_id=district_id,
            subject_id=subject_id,
        )

        schools = (
            await QuestionBankExpertRepo
            .list_schools_for_region(
                db,
                region_id=region_id,
            )
        )

        subjects = (
            await QuestionBankExpertRepo
            .list_active_subjects(db)
        )

        # --------------------------------------------------------
        # DISTRICTS
        # --------------------------------------------------------
        #
        # Районы уже присутствуют в результате schools.
        # Поэтому отдельный SQL-запрос к District не нужен.
        #
        # list_schools_for_region() возвращает школы в порядке:
        #
        #     District.name
        #     School.name
        #
        # dict сохраняет порядок вставки, поэтому районы также
        # останутся в порядке, подготовленном repository.
        # --------------------------------------------------------

        districts_by_id = {
            item.district_id: item.district_name
            for item in schools
        }

        districts = [
            QuestionBankExpertDistrictDTO(
                district_id=district_id,
                district_name=district_name,
            )
            for district_id, district_name
            in districts_by_id.items()
        ]

        return QuestionBankExpertPageDTO(
            region_id=region_id,

            districts=districts,

            experts=[
                QuestionBankExpertListItemDTO(
                    expert_id=item.expert_id,

                    iin=item.iin,
                    full_name=item.full_name,

                    school_id=item.school_id,
                    school_name=item.school_name,

                    district_id=item.district_id,
                    district_name=item.district_name,

                    region_id=item.region_id,
                    region_name=item.region_name,

                    subject_id=item.subject_id,
                    subject_name=item.subject_name,
                    specialty_id=item.specialty_id, specialty_name=item.specialty_name,
            specialty_name_kz=item.specialty_name_kz,

                    qualification_category_text=(
                        item.qualification_category_text
                    ),
                    ped_experience_years=(
                        item.ped_experience_years
                    ),

                    user_id=item.user_id,
                    has_account=item.user_id is not None,

                    is_active=item.is_active,

                    created_at=item.created_at,
                )
                for item in experts
            ],

            schools=[
                QuestionBankExpertSchoolDTO(
                    school_id=item.school_id,
                    school_name=item.school_name,

                    district_id=item.district_id,
                    district_name=item.district_name,
                )
                for item in schools
            ],

            subjects=[
                QuestionBankExpertSubjectDTO(
                    subject_id=item.subject_id,
                    code=item.code,
                    name=item.name,
                )
                for item in subjects
            ],
        )

    @classmethod
    async def get_form_options(
            cls,
            db: AsyncSession,
            *,
            region_id: int,
    ) -> QuestionBankExpertFormOptionsDTO:
        """
        Возвращает справочные данные для форм
        создания и редактирования эксперта.

        Выполняется фиксированное количество запросов:
            1. школы региона;
            2. активные предметы.

        Список экспертов не загружается.
        N+1 отсутствует.
        """

        cls._validate_region_id(region_id)

        schools = (
            await QuestionBankExpertRepo.list_schools_for_region(
                db,
                region_id=region_id,
            )
        )

        subjects = (
            await QuestionBankExpertRepo.list_active_subjects(db)
        )

        return QuestionBankExpertFormOptionsDTO(
            specialties=await cls.specialty_options(db),
            schools=[
                QuestionBankExpertSchoolDTO(
                    school_id=row.school_id,
                    school_name=row.school_name,
                    district_id=row.district_id,
                    district_name=row.district_name,
                )
                for row in schools
            ],
            subjects=[
                QuestionBankExpertSubjectDTO(
                    subject_id=row.subject_id,
                    code=row.code,
                    name=row.name,
                )
                for row in subjects
            ],
        )

    # ========================================================
    # DETAIL
    # ========================================================

    @classmethod
    async def get_detail(
            cls,
            db: AsyncSession,
            *,
            expert_id: int,
            region_id: int,
    ) -> QuestionBankExpertDetailDTO:

        cls._validate_id(
            expert_id,
            field_name="Сарапшы",
        )
        cls._validate_region_id(region_id)

        item = (
            await QuestionBankExpertRepo
            .get_detail_for_region(
                db,
                expert_id=expert_id,
                region_id=region_id,
            )
        )

        if item is None:
            raise QuestionBankExpertNotFoundError(
                "Сарапшы табылмады."
            )

        return QuestionBankExpertDetailDTO(
            expert_id=item.expert_id,

            iin=item.iin,
            full_name=item.full_name,

            phone=item.phone,
            email=item.email,

            school_id=item.school_id,
            school_name=item.school_name,

            district_id=item.district_id,
            district_name=item.district_name,

            region_id=item.region_id,
            region_name=item.region_name,

            subject_id=item.subject_id,
            subject_code=item.subject_code,
            subject_name=item.subject_name,
            specialty_id=item.specialty_id,
            specialty_name=item.specialty_name,
            specialty_name_kz=item.specialty_name_kz,

            position_text=item.position_text,
            education_text=item.education_text,
            specialty_text=item.specialty_text,

            qualification_category_text=(
                item.qualification_category_text
            ),

            ped_experience_years=(
                item.ped_experience_years
            ),

            user_id=item.user_id,
            has_account=item.user_id is not None,

            is_active=item.is_active,

            created_by_user_id=item.created_by_user_id,
            created_at=item.created_at,
            updated_at=item.updated_at,

            deactivated_by_user_id=(
                item.deactivated_by_user_id
            ),
            deactivated_at=item.deactivated_at,
        )

    # ========================================================
    # CREATE
    # ========================================================

    @classmethod
    async def create(
            cls,
            db: AsyncSession,
            *,
            region_id: int,
            created_by_user_id: int,
            dto: QuestionBankExpertCreateDTO,
    ) -> QuestionBankExpert:

        cls._validate_region_id(region_id)
        cls._validate_user_id(created_by_user_id)

        await cls.require_specialty(db, dto.specialty_id)

        cls._validate_experience(
            dto.ped_experience_years
        )

        iin = cls._normalize_iin(dto.iin)

        full_name = cls._normalize_required_text(
            dto.full_name,
            field_name="Сарапшының аты-жөні",
        )

        await cls._require_school_in_region(
            db,
            school_id=dto.school_id,
            region_id=region_id,
        )

        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": "qb-expert:" + iin})
        existing = (await db.execute(select(QuestionBankExpert).where(
            QuestionBankExpert.iin == iin,
            QuestionBankExpert.specialty_id == dto.specialty_id,
        ))).scalars().first()

        if existing is not None:
            raise QuestionBankExpertError(
                "Бұл ЖСН бойынша осы мамандыққа "
                "сарапшы бұрыннан тіркелген."
            )

        user_id = (
            await QuestionBankExpertRepo.get_active_user_id_by_iin(
                db,
                iin=iin,
            )
        )

        expert = QuestionBankExpert(
            school_id=dto.school_id,
            subject_id=None,
            specialty_id=dto.specialty_id,

            iin=iin,
            full_name=full_name,

            phone=cls._normalize_optional_text(
                dto.phone
            ),
            email=cls._normalize_optional_text(
                dto.email
            ),

            position_text=cls._normalize_optional_text(
                dto.position_text
            ),
            education_text=cls._normalize_optional_text(
                dto.education_text
            ),
            specialty_text=cls._normalize_optional_text(
                dto.specialty_text
            ),
            qualification_category_text=(
                cls._normalize_optional_text(
                    dto.qualification_category_text
                )
            ),

            ped_experience_years=(
                dto.ped_experience_years
            ),

            is_active=True,

            created_by_user_id=created_by_user_id,

            user_id=user_id,

            deactivated_by_user_id=None,
            deactivated_at=None,
        )

        try:
            await QuestionBankExpertRepo.add(
                db,
                expert=expert,
            )

            await QuestionBankExpertRepo.flush(db)

            await db.commit()
            await db.refresh(expert)

            return expert

        except IntegrityError as exc:
            await db.rollback()

            raise QuestionBankExpertError(
                "Сарапшыны сақтау мүмкін болмады. "
                "ЖСН мен мамандықтың қайталануын тексеріңіз."
            ) from exc

        except Exception:
            await db.rollback()
            raise

    # ========================================================
    # UPDATE
    # ========================================================

    @classmethod
    async def update(
            cls,
            db: AsyncSession,
            *,
            expert_id: int,
            region_id: int,
            dto: QuestionBankExpertUpdateDTO,
    ) -> None:

        cls._validate_id(
            expert_id,
            field_name="Сарапшы",
        )
        cls._validate_region_id(region_id)

        cls._validate_experience(
            dto.ped_experience_years
        )

        await cls._require_school_in_region(
            db,
            school_id=dto.school_id,
            region_id=region_id,
        )

        expert = await QuestionBankExpertRepo.get_entity_for_region(
            db,
            expert_id=expert_id,
            region_id=region_id,
        )

        if expert is None:
            raise QuestionBankExpertNotFoundError(
                "Сарапшы табылмады."
            )

        await cls.require_specialty(db, dto.specialty_id)
        # Preserve old subject metadata; authorization uses specialty_id only.
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                         {"key": "qb-expert:" + expert.iin})
        duplicate = (await db.execute(select(QuestionBankExpert.id).where(
            QuestionBankExpert.iin == expert.iin,
            QuestionBankExpert.specialty_id == dto.specialty_id,
            QuestionBankExpert.id != expert.id,
        ).limit(1))).scalar_one_or_none()
        if duplicate is not None and expert.specialty_id != dto.specialty_id:
            raise QuestionBankExpertError("Эта специальность уже назначена данному эксперту.")
        expert.specialty_id = dto.specialty_id
        expert.school_id = dto.school_id

        expert.full_name = cls._normalize_required_text(
            dto.full_name,
            field_name="Сарапшының аты-жөні",
        )

        expert.phone = cls._normalize_optional_text(
            dto.phone
        )

        expert.email = cls._normalize_optional_text(
            dto.email
        )

        expert.position_text = cls._normalize_optional_text(
            dto.position_text
        )

        expert.education_text = cls._normalize_optional_text(
            dto.education_text
        )

        expert.specialty_text = cls._normalize_optional_text(
            dto.specialty_text
        )

        expert.qualification_category_text = (
            cls._normalize_optional_text(
                dto.qualification_category_text
            )
        )

        expert.ped_experience_years = (
            dto.ped_experience_years
        )

        try:
            await QuestionBankExpertRepo.flush(db)
            await db.commit()

        except Exception:
            await db.rollback()
            raise

    # ========================================================
    # DEACTIVATE
    # ========================================================

    @classmethod
    async def deactivate(
            cls,
            db: AsyncSession,
            *,
            expert_id: int,
            region_id: int,
            deactivated_by_user_id: int,
    ) -> None:

        cls._validate_id(
            expert_id,
            field_name="Сарапшы",
        )
        cls._validate_region_id(region_id)
        cls._validate_user_id(
            deactivated_by_user_id
        )

        expert = await QuestionBankExpertRepo.get_entity_for_region(
            db,
            expert_id=expert_id,
            region_id=region_id,
        )

        if expert is None:
            raise QuestionBankExpertNotFoundError(
                "Сарапшы табылмады."
            )

        if not expert.is_active:
            raise QuestionBankExpertError(
                "Сарапшы реестрден бұрын шығарылған."
            )

        QuestionBankExpertRepo.deactivate(
            expert,
            deactivated_by_user_id=deactivated_by_user_id,
            deactivated_at=datetime.now(timezone.utc),
        )

        try:
            await QuestionBankExpertRepo.flush(db)
            await db.commit()

        except Exception:
            await db.rollback()
            raise

    # ========================================================
    # ACTIVATE
    # ========================================================

    @classmethod
    async def activate(
            cls,
            db: AsyncSession,
            *,
            expert_id: int,
            region_id: int,
    ) -> None:

        cls._validate_id(
            expert_id,
            field_name="Сарапшы",
        )
        cls._validate_region_id(region_id)

        expert = await QuestionBankExpertRepo.get_entity_for_region(
            db,
            expert_id=expert_id,
            region_id=region_id,
        )

        if expert is None:
            raise QuestionBankExpertNotFoundError(
                "Сарапшы табылмады."
            )

        if expert.is_active:
            raise QuestionBankExpertError(
                "Сарапшы қазірдің өзінде белсенді."
            )

        QuestionBankExpertRepo.activate(expert)

        try:
            await QuestionBankExpertRepo.flush(db)
            await db.commit()

        except Exception:
            await db.rollback()
            raise

    # ========================================================
    # EXPERT MODE
    # ========================================================

    @classmethod
    async def get_active_subject_ids_for_user(
            cls,
            db: AsyncSession,
            *,
            user_id: int,
    ) -> list[int]:

        cls._validate_user_id(user_id)

        return (
            await QuestionBankExpertRepo
            .list_active_subject_ids_for_user(
                db,
                user_id=user_id,
            )
        )

    @classmethod
    async def has_expert_mode(
            cls,
            db: AsyncSession,
            *,
            user_id: int,
    ) -> bool:

        cls._validate_user_id(user_id)

        return (
            await QuestionBankExpertRepo
            .has_active_expert_scope(
                db,
                user_id=user_id,
            )
        )

    # ========================================================
    # HUMAN REVIEW
    # ========================================================

    @classmethod
    async def get_review_page(
            cls,
            db: AsyncSession,
            *,
            user_id: int,
    ) -> TeacherQuestionReviewPageDTO:
        """
        Формирует очередь Human Review
        для текущего предметного эксперта.

        Право проверки определяется активными назначениями
        QuestionBankExpert текущего пользователя.

        Эксперт получает REVIEW-задания по предметам,
        доступным его специальностям, классам и языкам обучения.

        Собственные задания пользователя исключаются
        repository-слоем.
        """

        # ----------------------------------------------------
        # 1. BASIC VALIDATION
        # ----------------------------------------------------

        cls._validate_user_id(
            user_id
        )

        # ----------------------------------------------------
        # 2. EXPERT SUBJECT SCOPE
        # ----------------------------------------------------

        subject_ids = (
            await cls.get_active_subject_ids_for_user(
                db,
                user_id=user_id,
            )
        )

        # ----------------------------------------------------
        # 3. EMPTY EXPERT SCOPE
        # ----------------------------------------------------

        if not subject_ids:
            return TeacherQuestionReviewPageDTO(
                teaching_scope=[],
                items=[],
                total=0,
            )

        # ----------------------------------------------------
        # 4. REVIEW QUEUE
        # ----------------------------------------------------

        rows = (
            await TeacherQuestionBankRepo.list_review_queue(
                db,
                reviewer_user_id=user_id,
                subject_ids=subject_ids,
            )
        )

        # ----------------------------------------------------
        # 5. OBJECTIVES FOR WHOLE REVIEW QUEUE
        # ----------------------------------------------------

        item_ids = [
            row.item_id
            for row in rows
        ]

        objective_rows = (
            await TeacherQuestionBankRepo.list_objectives_for_items(
                db,
                item_ids=item_ids,
            )
        )

        objectives_by_item_id = (
            cls._group_objectives_by_item_id(
                objective_rows
            )
        )

        # ----------------------------------------------------
        # 6. DTO
        # ----------------------------------------------------

        items = [
            cls._build_review_item_dto(
                row,
                objectives=objectives_by_item_id.get(
                    row.item_id,
                    [],
                ),
            )
            for row in rows
        ]

        # ----------------------------------------------------
        # 7. RESULT
        # ----------------------------------------------------

        return TeacherQuestionReviewPageDTO(
            teaching_scope=[],
            items=items,
            total=len(items),
        )

    @classmethod
    async def _get_review_item_for_expert(
            cls,
            db: AsyncSession,
            *,
            item_id: int,
            reviewer_user_id: int,
    ) -> QuestionBankItem:
        """
        Возвращает задание, которое текущий предметный
        эксперт имеет право проверять.

        Проверяется:
        - reviewer имеет активное экспертное назначение;
        - предмет задания входит в expert scope;
        - задание находится в REVIEW;
        - reviewer не является автором задания.

        Конкретная причина отсутствия доступа наружу
        не раскрывается.
        """

        # ----------------------------------------------------
        # 1. BASIC VALIDATION
        # ----------------------------------------------------

        cls._validate_id(
            item_id,
            field_name="Задание",
        )

        cls._validate_user_id(
            reviewer_user_id
        )

        # ----------------------------------------------------
        # 2. EXPERT SUBJECT SCOPE
        # ----------------------------------------------------

        subject_ids = (
            await cls.get_active_subject_ids_for_user(
                db,
                user_id=reviewer_user_id,
            )
        )

        if not subject_ids:
            raise QuestionBankExpertError(
                "Задание недоступно для проверки."
            )

        # ----------------------------------------------------
        # 3. REVIEW ACCESS
        # ----------------------------------------------------

        item = (
            await TeacherQuestionBankRepo
            .get_review_item_for_reviewer(
                db,
                item_id=item_id,
                reviewer_user_id=reviewer_user_id,
                subject_ids=subject_ids,
            )
        )

        if item is None:
            raise QuestionBankExpertError(
                "Задание недоступно для проверки."
            )

        return item

    @classmethod
    async def approve_review(
            cls,
            db: AsyncSession,
            *,
            item_id: int,
            reviewer_user_id: int,
            comment: str | None = None,
    ) -> QuestionBankReviewCreateResult:
        """
        Одобряет задание в Human Review
        от имени предметного эксперта.

        Lifecycle:
            REVIEW -> READY

        Проверка экспертного доступа выполняется здесь.
        Сам domain lifecycle и создание review выполняет
        QuestionBankService.
        """

        item = await cls._get_review_item_for_expert(
            db,
            item_id=item_id,
            reviewer_user_id=reviewer_user_id,
        )

        return await QuestionBankService.approve(
            db,
            item_id=item.id,
            reviewer_user_id=reviewer_user_id,
            comment=comment,
        )

    @classmethod
    async def reject_review(
            cls,
            db: AsyncSession,
            *,
            item_id: int,
            reviewer_user_id: int,
            comment: str | None = None,
    ) -> QuestionBankReviewCreateResult:
        """
        Отклоняет задание в Human Review
        от имени предметного эксперта.

        Lifecycle:
            REVIEW -> REJECTED

        Проверка экспертного доступа выполняется здесь.
        Сам domain lifecycle и создание review выполняет
        QuestionBankService.
        """

        item = await cls._get_review_item_for_expert(
            db,
            item_id=item_id,
            reviewer_user_id=reviewer_user_id,
        )

        return await QuestionBankService.reject(
            db,
            item_id=item.id,
            reviewer_user_id=reviewer_user_id,
            comment=comment,
        )

    # ========================================================
    # HUMAN REVIEW MAPPERS
    # ========================================================

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

    @staticmethod
    def _resolve_item_quarter(
            objectives: list[
                TeacherQuestionBankObjectiveRow
            ],
    ) -> int:
        if not objectives:
            raise QuestionBankExpertError(
                "Задание не содержит учебных целей."
            )

        quarters = {
            objective.quarter
            for objective in objectives
        }

        if len(quarters) != 1:
            raise QuestionBankExpertError(
                "Учебные цели задания относятся "
                "к разным четвертям."
            )

        quarter = next(iter(quarters))

        if not 1 <= quarter <= 4:
            raise QuestionBankExpertError(
                "Некорректная четверть задания."
            )

        return quarter

    @classmethod
    def _build_review_item_dto(
            cls,
            row: TeacherQuestionReviewRow,
            *,
            objectives: list[
                TeacherQuestionBankObjectiveRow
            ],
    ) -> TeacherQuestionReviewItemDTO:
        """
        Преобразует read-model очереди Human Review
        в DTO страницы проверки.

        Четверть определяется через связанные
        LearningObjective.
        """

        quarter = cls._resolve_item_quarter(
            objectives
        )

        return TeacherQuestionReviewItemDTO(
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
            grading_settings=dict(row.grading_settings or {}),
            explanation=row.explanation,

            max_score=row.max_score,

            created_by_user_id=(
                row.created_by_user_id
            ),
            author_name=row.author_name,

            created_at=row.created_at,
            updated_at=row.updated_at,
        )
