# app/modules/assessment/repositories/question_bank_expert_repo.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.models_question_bank_experts import (
    QuestionBankExpert, QuestionBankExpertSpecialty, QuestionBankExpertRule,
)
from app.modules.education.models import Subject
from app.modules.org.models import District, Region, School
from app.modules.users.models import User


# ============================================================
# READ MODELS
# ============================================================


@dataclass(frozen=True, slots=True)
class QuestionBankExpertListRow:
    """
    Строка регионального реестра экспертов.

    Это projection/read model.
    ORM relationships для построения списка не используются.
    """

    expert_id: int

    iin: str
    full_name: str

    school_id: int
    school_name: str

    district_id: int
    district_name: str

    region_id: int
    region_name: str

    subject_id: int | None
    subject_name: str

    qualification_category_text: str | None
    ped_experience_years: int | None

    user_id: int | None
    is_active: bool

    created_at: datetime

    specialty_id: int | None = None
    specialty_name: str = "Требуется настройка"
    specialty_name_kz: str | None = None


@dataclass(frozen=True, slots=True)
class QuestionBankExpertDetail:
    """
    Полная карточка эксперта для административного интерфейса.
    """

    expert_id: int

    iin: str
    full_name: str
    phone: str | None
    email: str | None

    school_id: int
    school_name: str

    district_id: int
    district_name: str

    region_id: int
    region_name: str

    subject_id: int | None
    subject_code: str
    subject_name: str

    position_text: str | None
    education_text: str | None
    specialty_text: str | None
    qualification_category_text: str | None
    ped_experience_years: int | None

    user_id: int | None
    is_active: bool

    created_by_user_id: int
    created_at: datetime
    updated_at: datetime

    deactivated_by_user_id: int | None
    deactivated_at: datetime | None

    specialty_id: int | None = None
    specialty_name: str = "Требуется настройка"
    specialty_name_kz: str | None = None


@dataclass(frozen=True, slots=True)
class QuestionBankExpertExistingRow:
    """
    Минимальная projection существующего назначения.

    Используется при ручном создании и Excel-import.
    """

    expert_id: int
    iin: str
    subject_id: int | None
    school_id: int
    user_id: int | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class QuestionBankExpertSchoolLookupRow:
    """
    Школа, доступная региональному администратору.
    """

    school_id: int
    school_name: str
    district_id: int
    district_name: str
    region_id: int


@dataclass(frozen=True, slots=True)
class QuestionBankExpertSubjectLookupRow:
    """
    Предмет для формы / Excel-import.
    """

    subject_id: int | None
    code: str
    name: str


# ============================================================
# REPOSITORY
# ============================================================


class QuestionBankExpertRepo:
    """
    Repository предметных экспертов Question Bank.

    Архитектурные правила:

    - repository не выполняет commit / rollback;
    - business validation находится в Service Layer;
    - regional security boundary выражается непосредственно SQL;
    - ORM lazy loading не используется;
    - запросов внутри циклов нет;
    - списки строятся projection-запросами;
    - batch-методы используются для Excel-import.
    """

    # ========================================================
    # INTERNAL SQL EXPRESSIONS
    # ========================================================

    @staticmethod
    def _school_name_expr():
        return func.coalesce(
            School.name,
            "",
        )

    @staticmethod
    def _district_name_expr():
        return func.coalesce(
            District.name,
            "",
        )

    @staticmethod
    def _region_name_expr():
        return func.coalesce(
            Region.name,
            "",
        )

    @staticmethod
    def _subject_name_expr():
        return func.coalesce(
            Subject.name_kz,
            Subject.name_ru,
            "",
        )

    # ========================================================
    # REGIONAL REGISTRY
    # ========================================================

    @classmethod
    async def list_for_region(
            cls,
            db: AsyncSession,
            *,
            region_id: int,
            active_only: bool | None = None,
            district_id: int | None = None,
            subject_id: int | None = None,
    ) -> list[QuestionBankExpertListRow]:
        """
        Получает реестр экспертов конкретного региона.

        Security boundary:
            Expert
                -> School
                -> District
                -> Region

        region_id проверяется непосредственно в SQL.
        """

        stmt = (
            select(
                QuestionBankExpert.id.label("expert_id"),
                QuestionBankExpert.iin.label("iin"),
                QuestionBankExpert.full_name.label("full_name"),

                School.id.label("school_id"),
                cls._school_name_expr().label("school_name"),

                District.id.label("district_id"),
                cls._district_name_expr().label(
                    "district_name"
                ),

                Region.id.label("region_id"),
                cls._region_name_expr().label(
                    "region_name"
                ),

                Subject.id.label("subject_id"),
                QuestionBankExpert.specialty_id.label("specialty_id"),
                func.coalesce(QuestionBankExpertSpecialty.name_ru, "Требуется настройка").label("specialty_name"),
                QuestionBankExpertSpecialty.name_kz.label("specialty_name_kz"),
                cls._subject_name_expr().label(
                    "subject_name"
                ),

                QuestionBankExpert
                .qualification_category_text
                .label("qualification_category_text"),

                QuestionBankExpert
                .ped_experience_years
                .label("ped_experience_years"),

                QuestionBankExpert.user_id.label("user_id"),
                QuestionBankExpert.is_active.label("is_active"),
                QuestionBankExpert.created_at.label("created_at"),
            )
            .join(
                School,
                School.id == QuestionBankExpert.school_id,
            )
            .join(
                District,
                District.id == School.district_id,
            )
            .join(
                Region,
                Region.id == District.region_id,
            )
            .outerjoin(
                Subject,
                Subject.id == QuestionBankExpert.subject_id,
            ).outerjoin(QuestionBankExpertSpecialty, QuestionBankExpertSpecialty.id == QuestionBankExpert.specialty_id)
            .where(
                Region.id == region_id,
            )
        )

        if active_only is not None:
            stmt = stmt.where(
                QuestionBankExpert.is_active == active_only
            )

        if district_id is not None:
            stmt = stmt.where(
                District.id == district_id
            )

        if subject_id is not None:
            stmt = stmt.where(exists(select(1).select_from(QuestionBankExpertRule).where(
                QuestionBankExpertRule.specialty_id == QuestionBankExpert.specialty_id,
                QuestionBankExpertRule.subject_id == subject_id,
                QuestionBankExpertRule.is_active.is_(True),
            )))

        stmt = stmt.order_by(
            QuestionBankExpert.full_name.asc(),
            Subject.sort_order.asc(),
            Subject.name_kz.asc(),
            QuestionBankExpert.id.asc(),
        )

        result = await db.execute(stmt)

        return [
            QuestionBankExpertListRow(**row)
            for row in result.mappings().all()
        ]

    @staticmethod
    async def get_entity_for_region(
            db: AsyncSession,
            *,
            expert_id: int,
            region_id: int,
    ) -> QuestionBankExpert | None:
        stmt = (
            select(QuestionBankExpert)
            .join(
                School,
                School.id == QuestionBankExpert.school_id,
            )
            .join(
                District,
                District.id == School.district_id,
            )
            .where(
                QuestionBankExpert.id == expert_id,
                District.region_id == region_id,
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    @staticmethod
    async def list_unbound_active_experts(
            db: AsyncSession,
    ) -> list[QuestionBankExpert]:
        """
        Активные экспертные назначения,
        которые ещё не связаны с User.
        """

        stmt = (
            select(QuestionBankExpert)
            .where(
                QuestionBankExpert.user_id.is_(None),
                QuestionBankExpert.is_active.is_(True),
            )
            .order_by(QuestionBankExpert.id.asc())
        )

        result = await db.execute(stmt)

        return list(result.scalars().all())

    # ========================================================
    # DETAIL + REGIONAL SECURITY BOUNDARY
    # ========================================================

    @classmethod
    async def get_detail_for_region(
        cls,
        db: AsyncSession,
        *,
        expert_id: int,
        region_id: int,
    ) -> QuestionBankExpertDetail | None:
        """
        Полная карточка эксперта.

        Эксперт другого региона не возвращается.
        """

        stmt = (
            select(
                QuestionBankExpert.id.label("expert_id"),

                QuestionBankExpert.iin.label("iin"),
                QuestionBankExpert.full_name.label("full_name"),
                QuestionBankExpert.phone.label("phone"),
                QuestionBankExpert.email.label("email"),

                School.id.label("school_id"),
                cls._school_name_expr().label("school_name"),

                District.id.label("district_id"),
                cls._district_name_expr().label(
                    "district_name"
                ),

                Region.id.label("region_id"),
                cls._region_name_expr().label(
                    "region_name"
                ),

                Subject.id.label("subject_id"),
                Subject.code.label("subject_code"),
                QuestionBankExpert.specialty_id.label("specialty_id"),
                func.coalesce(QuestionBankExpertSpecialty.name_ru, "Требуется настройка").label("specialty_name"),
                QuestionBankExpertSpecialty.name_kz.label("specialty_name_kz"),
                cls._subject_name_expr().label(
                    "subject_name"
                ),

                QuestionBankExpert.position_text.label(
                    "position_text"
                ),
                QuestionBankExpert.education_text.label(
                    "education_text"
                ),
                QuestionBankExpert.specialty_text.label(
                    "specialty_text"
                ),
                QuestionBankExpert
                .qualification_category_text
                .label("qualification_category_text"),
                QuestionBankExpert
                .ped_experience_years
                .label("ped_experience_years"),

                QuestionBankExpert.user_id.label("user_id"),
                QuestionBankExpert.is_active.label("is_active"),

                QuestionBankExpert.created_by_user_id.label(
                    "created_by_user_id"
                ),
                QuestionBankExpert.created_at.label("created_at"),
                QuestionBankExpert.updated_at.label("updated_at"),

                QuestionBankExpert
                .deactivated_by_user_id
                .label("deactivated_by_user_id"),
                QuestionBankExpert
                .deactivated_at
                .label("deactivated_at"),
            )
            .join(
                School,
                School.id == QuestionBankExpert.school_id,
            )
            .join(
                District,
                District.id == School.district_id,
            )
            .join(
                Region,
                Region.id == District.region_id,
            )
            .outerjoin(
                Subject,
                Subject.id == QuestionBankExpert.subject_id,
            ).outerjoin(QuestionBankExpertSpecialty, QuestionBankExpertSpecialty.id == QuestionBankExpert.specialty_id)
            .where(
                QuestionBankExpert.id == expert_id,
                Region.id == region_id,
            )
        )

        result = await db.execute(stmt)
        row = result.mappings().one_or_none()

        if row is None:
            return None

        return QuestionBankExpertDetail(**row)

    # ========================================================
    # REGIONAL SCHOOL SECURITY
    # ========================================================

    @staticmethod
    async def school_belongs_to_region(
        db: AsyncSession,
        *,
        school_id: int,
        region_id: int,
    ) -> bool:
        """
        Проверяет принадлежность школы региону.

        Используется Service Layer перед созданием /
        изменением эксперта.
        """

        stmt = select(
            exists().where(
                School.id == school_id,
                School.district_id == District.id,
                District.region_id == region_id,
            )
        )

        result = await db.execute(stmt)

        return bool(result.scalar_one())

    # ========================================================
    # EXISTING ASSIGNMENT
    # ========================================================

    @staticmethod
    async def get_by_iin_subject(
        db: AsyncSession,
        *,
        iin: str,
        subject_id: int,
    ) -> QuestionBankExpert | None:
        """
        Получает назначение по уникальной бизнес-паре:

            iin + subject_id

        Возвращает ORM entity, потому что Service Layer
        может изменить существующую запись.
        """

        stmt = (
            select(QuestionBankExpert)
            .where(
                QuestionBankExpert.iin == iin,
                QuestionBankExpert.subject_id == subject_id,
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    @staticmethod
    async def exists_by_iin_subject(
        db: AsyncSession,
        *,
        iin: str,
        subject_id: int,
    ) -> bool:
        stmt = select(
            exists().where(
                QuestionBankExpert.iin == iin,
                QuestionBankExpert.subject_id == subject_id,
            )
        )

        result = await db.execute(stmt)

        return bool(result.scalar_one())

    # ========================================================
    # EXPERT ACCESS
    # ========================================================

    @staticmethod
    async def list_active_subject_ids_for_user(
        db: AsyncSession,
        *,
        user_id: int,
    ) -> list[int]:
        """
        Предметные экспертные полномочия пользователя.

        В дальнейшем именно этот метод заменит получение
        subject_ids через teaching load для Human Review.
        """

        from app.modules.assessment.helpers.question_bank_expert_scope import active_scope_subject_ids
        return await active_scope_subject_ids(db, user_id)

    @staticmethod
    async def has_active_expert_scope(
        db: AsyncSession,
        *,
        user_id: int,
        subject_id: int | None = None,
    ) -> bool:
        """
        Проверяет наличие активного экспертного полномочия.

        Если subject_id передан — проверяется конкретный предмет.
        """

        ids = await QuestionBankExpertRepo.list_active_subject_ids_for_user(db, user_id=user_id)
        return subject_id in ids if subject_id is not None else bool(ids)

    @staticmethod
    async def list_existing_for_import(
        db: AsyncSession,
        *,
        iins: set[str],
    ) -> list[QuestionBankExpertExistingRow]:
        """
        Пакетно получает существующие назначения для набора ИИН.

        Один SQL-запрос независимо от количества строк Excel.
        """

        if not iins:
            return []

        stmt = (
            select(
                QuestionBankExpert.id.label("expert_id"),
                QuestionBankExpert.iin.label("iin"),
                QuestionBankExpert.subject_id.label("subject_id"),
                QuestionBankExpert.school_id.label("school_id"),
                QuestionBankExpert.user_id.label("user_id"),
                QuestionBankExpert.is_active.label("is_active"),
            )
            .where(
                QuestionBankExpert.iin.in_(iins)
            )
            .order_by(
                QuestionBankExpert.iin.asc(),
                QuestionBankExpert.subject_id.asc(),
            )
        )

        result = await db.execute(stmt)

        return [
            QuestionBankExpertExistingRow(**row)
            for row in result.mappings().all()
        ]

    # ========================================================
    # BATCH: REGION SCHOOLS
    # ========================================================

    @classmethod
    async def list_schools_for_region(
        cls,
        db: AsyncSession,
        *,
        region_id: int,
    ) -> list[QuestionBankExpertSchoolLookupRow]:
        """
        Все школы региона для:
        - ручной формы;
        - Excel-import;
        - пакетной валидации.

        Школа не обязана иметь school_admin или staff.
        """

        stmt = (
            select(
                School.id.label("school_id"),
                cls._school_name_expr().label("school_name"),

                District.id.label("district_id"),
                cls._district_name_expr().label(
                    "district_name"
                ),

                District.region_id.label("region_id"),
            )
            .join(
                District,
                District.id == School.district_id,
            )
            .where(
                District.region_id == region_id,
            )
            .order_by(
                District.name.asc(),
                School.name.asc(),
                School.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return [
            QuestionBankExpertSchoolLookupRow(**row)
            for row in result.mappings().all()
        ]

    # ========================================================
    # BATCH: SUBJECTS
    # ========================================================

    @classmethod
    async def list_active_subjects(
        cls,
        db: AsyncSession,
    ) -> list[QuestionBankExpertSubjectLookupRow]:
        """
        Активные предметы для формы и Excel-import.
        """

        stmt = (
            select(
                Subject.id.label("subject_id"),
                Subject.code.label("code"),
                cls._subject_name_expr().label("name"),
            )
            .where(
                Subject.is_active.is_(True)
            )
            .order_by(
                Subject.sort_order.asc(),
                Subject.name_ru.asc(),
                Subject.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return [
            QuestionBankExpertSubjectLookupRow(**row)
            for row in result.mappings().all()
        ]

    # ========================================================
    # USER ACCOUNT LOOKUP
    # ========================================================

    @staticmethod
    async def get_active_user_id_by_iin(
            db: AsyncSession,
            *,
            iin: str,
    ) -> int | None:
        """
        Находит активный аккаунт School Monitor по ИИН.

        Используется для автоматической привязки
        экспертного назначения к существующему User.

        User.role намеренно не проверяется:
        экспертность является дополнительным capability,
        а не основной ролью пользователя.
        """

        stmt = (
            select(User.id)
            .where(
                User.iin == iin,
                User.is_active.is_(True),
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    @staticmethod
    async def list_active_user_ids_by_iins(
            db: AsyncSession,
            *,
            iins: set[str],
    ) -> dict[str, int]:
        """
        Пакетное сопоставление ИИН -> User.id.

        Предназначено для Excel-import.
        Один SQL-запрос на весь набор ИИН.
        """

        if not iins:
            return {}

        stmt = (
            select(
                User.iin,
                User.id,
            )
            .where(
                User.iin.in_(iins),
                User.is_active.is_(True),
            )
        )

        result = await db.execute(stmt)

        return {
            row.iin: row.id
            for row in result
        }

    # ========================================================
    # WRITE PRIMITIVES
    # ========================================================

    @staticmethod
    async def add(
        db: AsyncSession,
        *,
        expert: QuestionBankExpert,
    ) -> QuestionBankExpert:
        """
        Добавляет entity в Unit of Work.

        commit выполняет Service Layer.
        """

        db.add(expert)

        return expert

    @staticmethod
    async def flush(
        db: AsyncSession,
    ) -> None:
        await db.flush()

    @staticmethod
    def deactivate(
        expert: QuestionBankExpert,
        *,
        deactivated_by_user_id: int,
        deactivated_at: datetime,
    ) -> None:
        """
        Только mutation primitive.

        Право пользователя на деактивацию проверяет Service Layer.
        """

        expert.is_active = False
        expert.deactivated_by_user_id = deactivated_by_user_id
        expert.deactivated_at = deactivated_at

    @staticmethod
    def activate(
        expert: QuestionBankExpert,
    ) -> None:
        """
        Повторно активирует историческую запись.
        """

        expert.is_active = True
        expert.deactivated_by_user_id = None
        expert.deactivated_at = None

    @staticmethod
    def bind_user(
        expert: QuestionBankExpert,
        *,
        user_id: int | None,
    ) -> None:
        """
        Связывает экспертное назначение с аккаунтом.

        Один User может иметь несколько назначений по предметам.
        """

        expert.user_id = user_id
