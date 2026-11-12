from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


if TYPE_CHECKING:
    from app.modules.org.models import School
    from app.modules.users.models import User
    from app.modules.education.models import Subject


class QuestionBankExpert(Base):
    """
    Эксперт предметного сообщества Question Bank.

    Архитектурные правила:

    1. Экспертный реестр независим от SchoolStaffMember.

       Школа может существовать в справочнике School Monitor,
       даже если в ней ещё:
       - нет school_admin;
       - не настроен персонал;
       - не создан план ВШК;
       - не используется Assessment.

    2. Одна запись назначает специальность с правилами предмет/класс/язык обучения.
       subject_id сохраняется как историческое поле; новые назначения используют specialty_id.
       Несколько специальностей одного человека представлены несколькими записями.

    3. География не дублируется.

       В таблице хранится только school_id:

           QuestionBankExpert
               -> School
               -> District
               -> Region

       district_id и region_id здесь намеренно отсутствуют.

    4. user_id необязателен.

       Региональный администратор может внести эксперта
       в реестр до появления у него аккаунта School Monitor.

    5. Записи экспертов не удаляются при обычном исключении
       из экспертного сообщества.

       Используется:
           is_active = False
           deactivated_at
           deactivated_by_user_id

       Это сохраняет историю экспертных полномочий.

    6. Все ORM relationships используют lazy="raise".

       Repository обязан явно загружать необходимые данные
       через JOIN / joinedload / selectinload.
       Скрытый ORM I/O не допускается.
    """

    __tablename__ = "question_bank_experts"

    __table_args__ = (
        # Один человек не должен дважды иметь одно и то же
        # предметное экспертное назначение.
        UniqueConstraint(
            "iin",
            "subject_id",
            name="uq_qb_expert_iin_subject",
        ),

        # ИИН Казахстана — ровно 12 цифр.
        CheckConstraint(
            "iin ~ '^[0-9]{12}$'",
            name="ck_qb_expert_iin_12_digits",
        ),

        # Стаж не может быть отрицательным.
        CheckConstraint(
            "ped_experience_years IS NULL "
            "OR ped_experience_years >= 0",
            name="ck_qb_expert_ped_experience_non_negative",
        ),

        # Основные выборки регионального администратора
        # будут начинаться со школы.
        Index(
            "ix_qb_expert_school_active",
            "school_id",
            "is_active",
        ),

        # Очередь Human Review будет фильтроваться
        # по предмету эксперта.
        Index(
            "ix_qb_expert_subject_active",
            "subject_id",
            "is_active",
        ),

        # Быстрая проверка:
        # имеет ли авторизованный User экспертный режим.
        Index(
            "ix_qb_expert_user_active",
            "user_id",
            "is_active",
        ),

        # Поиск существующего эксперта при ручном вводе
        # и Excel-import.
        Index(
            "ix_qb_expert_iin_active",
            "iin",
            "is_active",
        ),
    )

    # =========================================================
    # ID
    # =========================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    # =========================================================
    # SCHOOL
    # =========================================================

    school_id: Mapped[int] = mapped_column(
        ForeignKey(
            "schools.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    # =========================================================
    # SUBJECT
    # =========================================================

    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "subjects.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    specialty_id: Mapped[int | None] = mapped_column(
        ForeignKey("qb_expert_specialties.id", name="fk_qb_expert_specialty", ondelete="RESTRICT"),
        nullable=True, index=True,
    )

    # =========================================================
    # PERSONAL DATA
    # =========================================================

    iin: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    phone: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # =========================================================
    # PROFESSIONAL DATA
    # =========================================================

    position_text: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    education_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    specialty_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    qualification_category_text: Mapped[str | None] = (
        mapped_column(
            String(255),
            nullable=True,
        )
    )

    ped_experience_years: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # =========================================================
    # USER ACCOUNT
    #
    # NULL означает:
    # эксперт уже находится в региональном реестре,
    # но ещё не связан с аккаунтом School Monitor.
    #
    # user_id НЕ unique:
    # один User может иметь несколько предметных
    # экспертных назначений.
    # =========================================================

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    # =========================================================
    # STATUS
    # =========================================================

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    # =========================================================
    # AUDIT: CREATION
    # =========================================================

    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # =========================================================
    # AUDIT: DEACTIVATION
    # =========================================================

    deactivated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    school: Mapped["School"] = relationship(
        "School",
        back_populates="question_bank_experts",
        lazy="raise",
    )

    subject: Mapped[Subject | None] = relationship(
        "Subject",
        lazy="raise",
    )

    user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[user_id],
        lazy="raise",
    )

    created_by_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[created_by_user_id],
        lazy="raise",
    )

    deactivated_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[deactivated_by_user_id],
        lazy="raise",
    )

    # =========================================================
    # REPRESENTATION
    # =========================================================

    def __repr__(self) -> str:
        return (
            "<QuestionBankExpert "
            f"id={self.id} "
            f"iin={self.iin!r} "
            f"subject_id={self.subject_id} "
            f"school_id={self.school_id} "
            f"user_id={self.user_id} "
            f"is_active={self.is_active}>"
        )


class QuestionBankExpertSpecialty(Base):
    __tablename__ = "qb_expert_specialties"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name_kz: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class QuestionBankExpertRule(Base):
    __tablename__ = "qb_expert_rules"
    __table_args__ = (
        CheckConstraint("grade_from BETWEEN 1 AND 12 AND grade_to BETWEEN grade_from AND 12",
                        name="ck_qb_expert_rule_grades"),
        CheckConstraint("instruction_language IN ('all','kz','ru','uz','ug','tg')",
                        name="ck_qb_expert_rule_language"),
        UniqueConstraint("specialty_id", "subject_id", "grade_from", "grade_to", "instruction_language",
                         name="uq_qb_expert_rule"),
        Index("ix_qb_expert_rule_scope", "specialty_id", "subject_id", "is_active"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    specialty_id: Mapped[int] = mapped_column(ForeignKey("qb_expert_specialties.id", ondelete="RESTRICT"),
                                              nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False)
    grade_from: Mapped[int] = mapped_column(Integer, nullable=False)
    grade_to: Mapped[int] = mapped_column(Integer, nullable=False)
    instruction_language: Mapped[str] = mapped_column(String(8), nullable=False, default="all", server_default="all")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
