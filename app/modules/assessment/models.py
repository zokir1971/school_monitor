# app/modules/assessment/models.py

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    and_,
    func,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, foreign

from app.db.base import Base
from app.db.types import (
    ASSESSMENT_ANSWER_STATUS_ENUM,
    ASSESSMENT_CHECKPOINT_ENUM,
    ASSESSMENT_GRADE_ENUM,
    ASSESSMENT_INPUT_MODE_ENUM,
    ASSESSMENT_MODE_ENUM,
    ASSESSMENT_PARTICIPATION_STATUS_ENUM,
    ASSESSMENT_QUESTION_TYPE_ENUM,
    ASSESSMENT_STATUS_ENUM,
    ASSESSMENT_TASK_LINK_TYPE_ENUM,
    ASSESSMENT_TYPE_ENUM,
    ASSESSMENT_LANGUAGE_ENUM,
    ASSESSMENT_BLUEPRINT_STATUS_ENUM,
    ASSESSMENT_QUESTION_DIFFICULTY_ENUM,
    QUESTION_BANK_ITEM_STATUS_ENUM,
    QUESTION_BANK_ITEM_ORIGIN_ENUM, AI_QUESTION_GENERATION_RUN_STATUS_ENUM, QUESTION_BANK_REVIEW_DECISION_ENUM,
)
from app.modules.assessment.enums import (
    AssessmentAnswerStatus,
    AssessmentCheckpoint,
    AssessmentGrade,
    AssessmentInputMode,
    AssessmentMode,
    AssessmentParticipationStatus,
    AssessmentQuestionType,
    AssessmentStatus,
    AssessmentTaskLinkType,
    AssessmentType,
    AssessmentLanguage,
    AssessmentBlueprintStatus,
    AssessmentQuestionDifficulty,
    QuestionBankItemStatus,
    QuestionBankItemOrigin, AIQuestionGenerationRunStatus, QuestionBankReviewDecision,
)

if TYPE_CHECKING:
    from app.modules.education.models import (
        SchoolClass,
        SchoolStudent,
        Subject,
    )
    from app.modules.org.models import School
    from app.modules.planning.models_month_plan import SchoolMonthPlanItem
    from app.modules.staff.models_staff_school import SchoolStaffMember
    from app.modules.users.models import User


# =========================================================
# ASSESSMENT BLUEPRINT
# =========================================================

class AssessmentBlueprint(Base):
    """
    Спецификация будущего ONLINE Assessment.

    Blueprint описывает структуру будущей оценочной работы,
    но сам не является Assessment.

    Может многократно использоваться для создания
    конкретных Assessment в разных школах и классах.
    """

    __tablename__ = "assessment_blueprints"

    __table_args__ = (
        CheckConstraint(
            "grade_level BETWEEN 1 AND 12",
            name="ck_assessment_blueprints_grade_level",
        ),
        CheckConstraint(
            "question_count > 0",
            name="ck_assessment_blueprints_question_count_positive",
        ),
        CheckConstraint(
            "max_score > 0",
            name="ck_assessment_blueprints_max_score_positive",
        ),
        CheckConstraint(
            "duration_minutes IS NULL OR duration_minutes > 0",
            name="ck_assessment_blueprints_duration_minutes_positive",
        ),

        Index(
            "ix_assessment_blueprints_subject_grade_status",
            "subject_id",
            "grade_level",
            "status",
        ),
        Index(
            "ix_assessment_blueprints_creator",
            "created_by_user_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    # =====================================================
    # EDUCATION SCOPE
    # =====================================================

    subject_id: Mapped[int] = mapped_column(
        ForeignKey(
            "subjects.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    grade_level: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    # =====================================================
    # CONTENT
    # =====================================================

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # =====================================================
    # CLASSIFICATION
    # =====================================================

    assessment_type: Mapped[AssessmentType] = mapped_column(
        ASSESSMENT_TYPE_ENUM,
        nullable=False,
        default=AssessmentType.DIAGNOSTIC,
    )

    assessment_mode: Mapped[AssessmentMode] = mapped_column(
        ASSESSMENT_MODE_ENUM,
        nullable=False,
        default=AssessmentMode.WITHOUT_OBJECTIVES,
    )

    language: Mapped[AssessmentLanguage] = mapped_column(
        ASSESSMENT_LANGUAGE_ENUM,
        nullable=False,
        default=AssessmentLanguage.KAZAKH,
    )

    status: Mapped[AssessmentBlueprintStatus] = mapped_column(
        ASSESSMENT_BLUEPRINT_STATUS_ENUM,
        nullable=False,
        default=AssessmentBlueprintStatus.DRAFT,
    )

    # =====================================================
    # STRUCTURE
    # =====================================================

    question_count: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    max_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    duration_minutes: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
    )

    # =====================================================
    # EXTENSIBLE SETTINGS
    # =====================================================

    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa_text("'{}'::jsonb"),
    )

    # =====================================================
    # AUDIT
    # =====================================================

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
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

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    subject: Mapped["Subject"] = relationship(
        "Subject",
        back_populates="assessment_blueprints",
        lazy="raise",
    )

    created_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[created_by_user_id],
        lazy="raise",
    )

    objectives: Mapped[
        list["AssessmentBlueprintObjective"]
    ] = relationship(
        "AssessmentBlueprintObjective",
        back_populates="blueprint",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssessmentBlueprintObjective.order_no.asc()",
        lazy="raise",
    )

    question_types: Mapped[
        list["AssessmentBlueprintQuestionType"]
    ] = relationship(
        "AssessmentBlueprintQuestionType",
        back_populates="blueprint",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssessmentBlueprintQuestionType.order_no.asc()",
        lazy="raise",
    )

    assessments: Mapped[list["Assessment"]] = relationship(
        "Assessment",
        back_populates="blueprint",
        lazy="raise",
    )

    ai_generation_runs: Mapped[
        list["AIQuestionGenerationRun"]
    ] = relationship(
        "AIQuestionGenerationRun",
        back_populates="blueprint",
        passive_deletes=True,
        lazy="raise",
        order_by=(
            "AIQuestionGenerationRun.started_at.desc()"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AssessmentBlueprint "
            f"id={self.id} "
            f"subject_id={self.subject_id} "
            f"grade_level={self.grade_level} "
            f"status={self.status.value!r}>"
        )


# =========================================================
# ASSESSMENT BLUEPRINT OBJECTIVE
# =========================================================


class AssessmentBlueprintObjective(Base):
    """
    Учебная цель, включённая в Blueprint.

    Определяет планируемое количество заданий
    и суммарный максимальный балл по цели.
    """

    __tablename__ = "assessment_blueprint_objectives"

    __table_args__ = (
        UniqueConstraint(
            "blueprint_id",
            "learning_objective_id",
            name="uq_blueprint_objective_learning",
        ),
        UniqueConstraint(
            "blueprint_id",
            "order_no",
            name="uq_blueprint_objective_order",
        ),

        CheckConstraint(
            "question_count > 0",
            name="ck_blueprint_objective_question_count_positive",
        ),
        CheckConstraint(
            "max_score > 0",
            name="ck_blueprint_objective_max_score_positive",
        ),
        CheckConstraint(
            "order_no > 0",
            name="ck_blueprint_objective_order_positive",
        ),

        Index(
            "ix_blueprint_objectives_learning_objective",
            "learning_objective_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    blueprint_id: Mapped[int] = mapped_column(
        ForeignKey(
            "assessment_blueprints.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    learning_objective_id: Mapped[int] = mapped_column(
        ForeignKey(
            "learning_objectives.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    question_count: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    max_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    order_no: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    blueprint: Mapped["AssessmentBlueprint"] = relationship(
        "AssessmentBlueprint",
        back_populates="objectives",
        lazy="raise",
    )

    learning_objective: Mapped["LearningObjective"] = relationship(
        "LearningObjective",
        back_populates="blueprint_objectives",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<AssessmentBlueprintObjective "
            f"id={self.id} "
            f"blueprint_id={self.blueprint_id} "
            f"learning_objective_id={self.learning_objective_id} "
            f"order_no={self.order_no}>"
        )


# =========================================================
# ASSESSMENT BLUEPRINT QUESTION TYPE
# =========================================================


class AssessmentBlueprintQuestionType(Base):
    """
    Распределение типов заданий внутри Blueprint.

    Например:

        SINGLE_CHOICE      6 / 6 баллов
        MULTIPLE_CHOICE    3 / 6 баллов
        MATCHING           3 / 6 баллов
    """

    __tablename__ = "assessment_blueprint_question_types"

    __table_args__ = (
        UniqueConstraint(
            "blueprint_id",
            "question_type",
            name="uq_blueprint_question_type",
        ),
        UniqueConstraint(
            "blueprint_id",
            "order_no",
            name="uq_blueprint_question_type_order",
        ),

        CheckConstraint(
            "question_count > 0",
            name="ck_blueprint_question_type_count_positive",
        ),
        CheckConstraint(
            "max_score > 0",
            name="ck_blueprint_question_type_score_positive",
        ),
        CheckConstraint(
            "order_no > 0",
            name="ck_blueprint_question_type_order_positive",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    blueprint_id: Mapped[int] = mapped_column(
        ForeignKey(
            "assessment_blueprints.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    question_type: Mapped[AssessmentQuestionType] = mapped_column(
        ASSESSMENT_QUESTION_TYPE_ENUM,
        nullable=False,
    )

    question_count: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    max_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    order_no: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    blueprint: Mapped["AssessmentBlueprint"] = relationship(
        "AssessmentBlueprint",
        back_populates="question_types",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<AssessmentBlueprintQuestionType "
            f"id={self.id} "
            f"blueprint_id={self.blueprint_id} "
            f"question_type={self.question_type.value!r} "
            f"order_no={self.order_no}>"
        )


# =========================================================
# ASSESSMENT
# =========================================================


class Assessment(Base):
    """
    Оценочная / диагностическая работа.

    Assessment является самостоятельным объектом
    и не обязан быть связан:
        - с кампанией;
        - с задачей ВШК.

    Один Assessment:
        - принадлежит одной школе;
        - относится к одному предмету;
        - может охватывать несколько классов;
        - использует ручной или онлайн-режим;
        - может входить в AssessmentCampaign.

    assessment_mode определяет структуру работы:

        WITHOUT_OBJECTIVES
            - учебные цели не используются;

        ASSESSMENT_BY_SECTION
            - БЖБ / СОР;
            - учебные цели обязательны;

        ASSESSMENT_BY_QUARTER
            - ТЖБ / СОЧ;
            - учебные цели обязательны.

    duration_minutes хранит фактическую
    длительность конкретного Assessment.

    max_score может быть NULL только
    на стадии черновика.

    Перед READY / ACTIVE сервис обязан
    установить и проверить максимальный балл.
    """

    __tablename__ = "assessments"

    __table_args__ = (
        UniqueConstraint("diagnostic_subject_id", "school_id", "diagnostic_variant", "diagnostic_language", name="uq_assessment_diagnostic_context"),
        CheckConstraint("(diagnostic_subject_id IS NULL AND diagnostic_variant IS NULL AND diagnostic_language IS NULL) OR (diagnostic_subject_id IS NOT NULL AND diagnostic_variant IS NOT NULL AND diagnostic_language IS NOT NULL AND diagnostic_variant > 0 AND diagnostic_language IN ('ru','kk'))", name="ck_assessment_diagnostic_context"),
        # =================================================
        # UNIQUE / SCHOOL BOUNDARY
        # =================================================

        # Нужен как целевой уникальный ключ
        # для составных FK других Assessment-сущностей.
        UniqueConstraint(
            "id",
            "school_id",
            name="uq_assessments_id_school",
        ),

        # Кампания и Assessment обязаны
        # принадлежать одной школе.
        ForeignKeyConstraint(
            [
                "campaign_id",
                "school_id",
            ],
            [
                "assessment_campaigns.id",
                "assessment_campaigns.school_id",
            ],
            name="fk_assessment_campaign_school",
            ondelete="RESTRICT",
        ),

        # =================================================
        # CHECKS
        # =================================================

        CheckConstraint(
            "max_score IS NULL OR max_score > 0",
            name="ck_assessments_max_score_positive",
        ),

        CheckConstraint(
            """
            duration_minutes IS NULL
            OR duration_minutes > 0
            """,
            name=(
                "ck_assessments_duration_minutes_positive"
            ),
        ),

        # =================================================
        # INDEXES
        # =================================================
        Index(
            "ix_assessments_school_status",
            "school_id",
            "status",
        ),

        Index(
            "ix_assessments_school_subject",
            "school_id",
            "subject_id",
        ),

        Index(
            "ix_assessments_creator_created",
            "created_by_user_id",
            "created_at",
        ),

        Index(
            "ix_assessments_school_created",
            "school_id",
            "created_at",
        ),

        Index(
            "ix_assessments_campaign",
            "campaign_id",
        ),

        Index(
            "ix_assessments_blueprint_id",
            "blueprint_id",
        ),
    )

    # =====================================================
    # IDENTITY
    # =====================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    diagnostic_subject_id: Mapped[int | None] = mapped_column(ForeignKey('diagnostic_subjects.id', name='fk_assessment_diagnostic_subject', ondelete='RESTRICT'), nullable=True)
    diagnostic_variant: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diagnostic_language: Mapped[str | None] = mapped_column(String(2), nullable=True)

    school_id: Mapped[int] = mapped_column(
        ForeignKey(
            "schools.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    campaign_id: Mapped[
        int | None
        ] = mapped_column(
        Integer,
        nullable=True,
    )

    subject_id: Mapped[int] = mapped_column(
        ForeignKey(
            "subjects.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    blueprint_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "assessment_blueprints.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    created_by_user_id: Mapped[
        int | None
        ] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    # =====================================================
    # CONTENT
    # =====================================================

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[
        str | None
        ] = mapped_column(
        Text,
        nullable=True,
    )

    subject_name_snapshot: Mapped[
        str | None
        ] = mapped_column(
        String(255),
        nullable=True,
    )

    # =====================================================
    # TYPE / MODE
    # =====================================================

    assessment_type: Mapped[
        AssessmentType
    ] = mapped_column(
        ASSESSMENT_TYPE_ENUM,
        nullable=False,
        default=AssessmentType.DIAGNOSTIC,
    )

    assessment_mode: Mapped[
        AssessmentMode
    ] = mapped_column(
        ASSESSMENT_MODE_ENUM,
        nullable=False,
        default=(
            AssessmentMode.WITHOUT_OBJECTIVES
        ),
    )

    checkpoint: Mapped[
        AssessmentCheckpoint | None
        ] = mapped_column(
        ASSESSMENT_CHECKPOINT_ENUM,
        nullable=True,
    )

    input_mode: Mapped[
        AssessmentInputMode
    ] = mapped_column(
        ASSESSMENT_INPUT_MODE_ENUM,
        nullable=False,
        default=AssessmentInputMode.MANUAL,
    )

    status: Mapped[
        AssessmentStatus
    ] = mapped_column(
        ASSESSMENT_STATUS_ENUM,
        nullable=False,
        default=AssessmentStatus.DRAFT,
    )

    # =====================================================
    # SCORING
    # =====================================================

    max_score: Mapped[
        Decimal | None
        ] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    # =====================================================
    # SETTINGS
    # =====================================================

    settings: Mapped[
        dict[str, Any]
    ] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa_text(
            "'{}'::jsonb"
        ),
    )

    # =====================================================
    # TIMING
    # =====================================================

    duration_minutes: Mapped[
        int | None
        ] = mapped_column(
        SmallInteger,
        nullable=True,
    )

    scheduled_at: Mapped[
        datetime | None
        ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    started_at: Mapped[
        datetime | None
        ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[
        datetime | None
        ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # =====================================================
    # AUDIT
    # =====================================================

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

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    school: Mapped["School"] = relationship(
        "School",
        lazy="raise",
    )

    campaign: Mapped[
        "AssessmentCampaign | None"
    ] = relationship(
        "AssessmentCampaign",

        primaryjoin=lambda: and_(
            foreign(
                Assessment.campaign_id
            )
            == AssessmentCampaign.id,

            Assessment.school_id
            == AssessmentCampaign.school_id,
        ),

        foreign_keys=lambda: [
            Assessment.campaign_id,
        ],

        back_populates="assessments",

        lazy="raise",
    )

    subject: Mapped["Subject"] = relationship(
        "Subject",
        lazy="raise",
    )

    created_by_user: Mapped[
        "User | None"
    ] = relationship(
        "User",
        foreign_keys=[
            created_by_user_id,
        ],
        lazy="raise",
    )

    groups: Mapped[
        list["AssessmentGroup"]
    ] = relationship(
        "AssessmentGroup",
        back_populates="assessment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssessmentGroup.id.asc()",
        lazy="raise",
    )

    objectives: Mapped[
        list["AssessmentObjective"]
    ] = relationship(
        "AssessmentObjective",
        back_populates="assessment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=(
            "AssessmentObjective.order_no.asc()"
        ),
        lazy="raise",
    )

    questions: Mapped[
        list["AssessmentQuestion"]
    ] = relationship(
        "AssessmentQuestion",
        back_populates="assessment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=(
            "AssessmentQuestion.order_no.asc()"
        ),
        lazy="raise",
    )

    task_links: Mapped[
        list["AssessmentTaskLink"]
    ] = relationship(
        "AssessmentTaskLink",
        back_populates="assessment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )

    blueprint: Mapped["AssessmentBlueprint | None"] = relationship(
        "AssessmentBlueprint",
        back_populates="assessments",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<Assessment "
            f"id={self.id} "
            f"school_id={self.school_id} "
            f"subject_id={self.subject_id} "
            f"assessment_mode="
            f"{self.assessment_mode.value!r} "
            f"status={self.status.value!r}>"
        )


# =========================================================
# ASSESSMENT GROUP
# =========================================================

class AssessmentGroup(Base):
    """
    Класс, участвующий в Assessment.

    school_id дублируется намеренно: составные FK гарантируют,
    что Assessment и SchoolClass принадлежат одной школе.

    Snapshot-поля фиксируют состояние класса на момент
    создания Assessment и используются для исторической
    аналитики независимо от дальнейших изменений SchoolClass.
    """

    __tablename__ = "assessment_groups"

    __table_args__ = (
        UniqueConstraint(
            "id",
            "school_id",
            name="uq_assessment_groups_id_school",
        ),
        UniqueConstraint(
            "assessment_id",
            "school_class_id",
            name="uq_assessment_group_class",
        ),
        ForeignKeyConstraint(
            ["assessment_id", "school_id"],
            [
                "assessments.id",
                "assessments.school_id",
            ],
            name="fk_assessment_group_assessment_school",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["school_class_id", "school_id"],
            [
                "school_classes.id",
                "school_classes.school_id",
            ],
            name="fk_assessment_group_class_school",
            ondelete="RESTRICT",
        ),

        Index(
            "ix_assessment_groups_class",
            "school_class_id",
        ),
        Index(
            "ix_assessment_groups_teacher",
            "teacher_staff_member_id",
        ),
        Index(
            "ix_assessment_groups_school",
            "school_id",
        ),

        # Для фильтрации и аналитики
        # Assessment по школе и параллели.
        Index(
            "ix_assessment_groups_school_grade",
            "school_id",
            "grade_level_snapshot",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey(
            "schools.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    assessment_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    school_class_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    teacher_staff_member_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "school_staff_members.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    # =====================================================
    # CLASS SNAPSHOT
    # =====================================================

    class_name_snapshot: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    grade_level_snapshot: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    academic_year_start_snapshot: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    teacher_name_snapshot: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # =====================================================
    # AUDIT
    # =====================================================

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    assessment: Mapped[Assessment] = relationship(
        "Assessment",
        back_populates="groups",
        primaryjoin=(
            "AssessmentGroup.assessment_id == Assessment.id"
        ),
        foreign_keys="[AssessmentGroup.assessment_id]",
        lazy="raise",
    )

    school_class: Mapped[SchoolClass] = relationship(
        "SchoolClass",
        primaryjoin=(
            "AssessmentGroup.school_class_id == SchoolClass.id"
        ),
        foreign_keys="[AssessmentGroup.school_class_id]",
        lazy="raise",
    )

    teacher_staff_member: Mapped[
        SchoolStaffMember | None
        ] = relationship(
        "SchoolStaffMember",
        foreign_keys=[teacher_staff_member_id],
        lazy="raise",
    )

    students: Mapped[list[AssessmentStudent]] = relationship(
        "AssessmentStudent",
        back_populates="assessment_group",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssessmentStudent.id.asc()",
        lazy="raise",
    )


# =========================================================
# ASSESSMENT STUDENT
# =========================================================


class AssessmentStudent(Base):
    """
    Участник конкретной Assessment-работы.

    Ссылка на SchoolStudent дает долгосрочную траекторию ученика,
    а student_name_snapshot сохраняет историческое отображение.

    school_id составными FK гарантирует, что участник, группа
    Assessment и SchoolStudent принадлежат одной школе.
    """

    __tablename__ = "assessment_students"

    __table_args__ = (
        UniqueConstraint(
            "assessment_group_id",
            "student_id",
            name="uq_assessment_student_group_student",
        ),
        ForeignKeyConstraint(
            ["assessment_group_id", "school_id"],
            [
                "assessment_groups.id",
                "assessment_groups.school_id",
            ],
            name="fk_assessment_student_group_school",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["student_id", "school_id"],
            [
                "school_students.id",
                "school_students.school_id",
            ],
            name="fk_assessment_student_student_school",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_assessment_students_group_status",
            "assessment_group_id",
            "participation_status",
        ),
        Index(
            "ix_assessment_students_student",
            "student_id",
        ),
        Index(
            "ix_assessment_students_school",
            "school_id",
        ),
        Index(
            "uq_assessment_student_access_token_hash",
            "access_token_hash",
            unique=True,
            postgresql_where=sa_text(
                "access_token_hash IS NOT NULL"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey(
            "schools.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    assessment_group_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    student_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    student_name_snapshot: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    participation_status: Mapped[
        AssessmentParticipationStatus
    ] = mapped_column(
        ASSESSMENT_PARTICIPATION_STATUS_ENUM,
        nullable=False,
        default=AssessmentParticipationStatus.ASSIGNED,
    )

    # Храним только хэш будущего одноразового/временного
    # онлайн-доступа ученика, а не сам токен.
    access_token_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    assessment_group: Mapped[AssessmentGroup] = relationship(
        "AssessmentGroup",
        back_populates="students",
        primaryjoin=(
            "AssessmentStudent.assessment_group_id "
            "== AssessmentGroup.id"
        ),
        foreign_keys="[AssessmentStudent.assessment_group_id]",
        lazy="raise",
    )

    student: Mapped[SchoolStudent] = relationship(
        "SchoolStudent",
        primaryjoin=(
            "AssessmentStudent.student_id == SchoolStudent.id"
        ),
        foreign_keys="[AssessmentStudent.student_id]",
        lazy="raise",
    )

    result: Mapped[AssessmentResult | None] = relationship(
        "AssessmentResult",
        back_populates="assessment_student",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
        lazy="raise",
    )

    answers: Mapped[list[AssessmentStudentAnswer]] = relationship(
        "AssessmentStudentAnswer",
        back_populates="assessment_student",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )


# =========================================================
# LEARNING OBJECTIVE
# =========================================================


class LearningObjective(Base):
    """
    Глобальный справочник учебных целей.

    Учебные цели после использования не удаляются физически:
    для прекращения использования применяется is_active=False.
    """

    __tablename__ = "learning_objectives"

    __table_args__ = (
        ForeignKeyConstraint(
            ["program_id", "subject_id"],
            ["learning_objective_programs.id", "learning_objective_programs.subject_id"],
            name="fk_lo_program_subject", ondelete="RESTRICT",
        ),
        CheckConstraint(
            "language_skill IS NULL OR language_skill IN ("
            "'listening','speaking','reading','writing',"
            "'listening_speaking','language_norms','language_skills')",
            name='ck_lo_language_skill',
        ),
        CheckConstraint("education_track IN ('','emn','ogn') AND (education_track = '' OR grade_level IN (10,11))",
                        name="ck_lo_education_track"),
        Index("ix_lo_program_grade_skill", "program_id", "grade_level", "language_skill"),

        UniqueConstraint(
            'program_id', 'subject_id', 'grade_level', 'code', 'education_track',
            name='uq_lo_program_subject_grade_code_track',
        ),
        Index(
            'uq_lo_legacy_subject_grade_code_track',
            'subject_id', 'grade_level', 'code', 'education_track',
            unique=True,
            postgresql_where=sa_text('program_id IS NULL'),
        ),
        CheckConstraint(
            "grade_level >= 1 AND grade_level <= 12",
            name="ck_learning_objectives_grade_level",
        ),
        CheckConstraint(
            "quarter >= 1 AND quarter <= 4",
            name="ck_learning_objectives_quarter",
        ),
        Index(
            "ix_learning_objectives_subject_grade_quarter_active",
            "subject_id",
            "grade_level",
            "quarter",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    subject_id: Mapped[int] = mapped_column(
        ForeignKey(
            "subjects.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    grade_level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    quarter: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Learning objective reference stage 1.
    program_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    subsection_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    section_title_kz: Mapped[str | None] = mapped_column(Text, nullable=True)
    section_title_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
    subsection_title_kz: Mapped[str | None] = mapped_column(Text, nullable=True)
    subsection_title_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
    language_skill: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_pages_kz: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list,
                                                       server_default=sa_text("'[]'::jsonb"))
    source_cells_kz: Mapped[list[dict] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    source_pages_ru: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list,
                                                       server_default=sa_text("'[]'::jsonb"))
    source_cells_ru: Mapped[list[dict] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Empty track preserves legacy objectives; named tracks apply only to 10/11.
    education_track: Mapped[str] = mapped_column(String(3), nullable=False, default="", server_default=sa_text("''"))
    title_segments_kz: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list,
                                                          server_default=sa_text("'[]'::jsonb"))
    title_segments_ru: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list,
                                                          server_default=sa_text("'[]'::jsonb"))
    has_formula_kz: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                 server_default=sa_text("false"))
    has_formula_ru: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                 server_default=sa_text("false"))
    formula_reviewed_kz: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                      server_default=sa_text("false"))
    formula_reviewed_ru: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                      server_default=sa_text("false"))

    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    title_kz: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    title_ru: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sa_text("true"),
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

    subject: Mapped["Subject"] = relationship(
        "Subject",
        lazy="raise",
    )

    assessment_objectives: Mapped[
        list["AssessmentObjective"]
    ] = relationship(
        "AssessmentObjective",
        back_populates="learning_objective",
        lazy="raise",
    )

    blueprint_objectives: Mapped[
        list["AssessmentBlueprintObjective"]
    ] = relationship(
        "AssessmentBlueprintObjective",
        back_populates="learning_objective",
        lazy="raise",
    )

    question_bank_item_objectives: Mapped[
        list["QuestionBankItemObjective"]
    ] = relationship(
        "QuestionBankItemObjective",
        back_populates="learning_objective",
        lazy="raise",
    )

# =========================================================
# ASSESSMENT OBJECTIVE
# =========================================================


class AssessmentObjective(Base):
    """
    Учебная цель, включенная в конкретный Assessment.

    code_snapshot/title_snapshot сохраняют исторический текст,
    даже если справочник учебных целей позже будет изменен.

    После появления результатов цель не удаляется:
    AssessmentObjectiveResult использует ON DELETE RESTRICT.
    """

    __tablename__ = "assessment_objectives"

    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "learning_objective_id",
            name="uq_assessment_objective_learning_objective",
        ),
        UniqueConstraint(
            "assessment_id",
            "order_no",
            name="uq_assessment_objective_order",
        ),
        CheckConstraint(
            "max_score > 0",
            name="ck_assessment_objectives_max_score_positive",
        ),
        CheckConstraint(
            "order_no > 0",
            name="ck_assessment_objectives_order_positive",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    assessment_id: Mapped[int] = mapped_column(
        ForeignKey(
            "assessments.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    learning_objective_id: Mapped[int] = mapped_column(
        ForeignKey(
            "learning_objectives.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    code_snapshot: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    title_snapshot: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    max_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    order_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    assessment: Mapped[Assessment] = relationship(
        "Assessment",
        back_populates="objectives",
        lazy="raise",
    )

    learning_objective: Mapped[LearningObjective] = relationship(
        "LearningObjective",
        back_populates="assessment_objectives",
        lazy="raise",
    )

    questions: Mapped[list[AssessmentQuestion]] = relationship(
        "AssessmentQuestion",
        back_populates="assessment_objective",
        lazy="raise",
    )

    objective_results: Mapped[
        list[AssessmentObjectiveResult]
    ] = relationship(
        "AssessmentObjectiveResult",
        back_populates="assessment_objective",
        lazy="raise",
    )


# =========================================================
# ASSESSMENT RESULT
# =========================================================


class AssessmentResult(Base):
    """
    Итоговый результат одного ученика.

    score/max_score/percent/grade являются историческим снимком
    результата на момент расчета.
    """

    __tablename__ = "assessment_results"

    __table_args__ = (
        UniqueConstraint(
            "assessment_student_id",
            name="uq_assessment_result_student",
        ),
        CheckConstraint(
            "score >= 0",
            name="ck_assessment_results_score_non_negative",
        ),
        CheckConstraint(
            "max_score > 0",
            name="ck_assessment_results_max_score_positive",
        ),
        CheckConstraint(
            "score <= max_score",
            name="ck_assessment_results_score_max",
        ),
        CheckConstraint(
            "percent >= 0 AND percent <= 100",
            name="ck_assessment_results_percent_range",
        ),
        Index(
            "ix_assessment_results_grade",
            "grade",
        ),
        Index(
            "ix_assessment_results_calculated_at",
            "calculated_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    assessment_student_id: Mapped[int] = mapped_column(
        ForeignKey(
            "assessment_students.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    score: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    max_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    percent: Mapped[Decimal] = mapped_column(
        Numeric(7, 4),
        nullable=False,
    )

    grade: Mapped[AssessmentGrade] = mapped_column(
        ASSESSMENT_GRADE_ENUM,
        nullable=False,
    )

    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
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

    assessment_student: Mapped[AssessmentStudent] = relationship(
        "AssessmentStudent",
        back_populates="result",
        lazy="raise",
    )

    objective_results: Mapped[
        list[AssessmentObjectiveResult]
    ] = relationship(
        "AssessmentObjectiveResult",
        back_populates="assessment_result",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )


# =========================================================
# OBJECTIVE RESULT
# =========================================================


class AssessmentObjectiveResult(Base):
    """
    Исторический результат ученика по одной учебной цели.

    assessment_objective_id использует RESTRICT:
    цель Assessment нельзя физически удалить, если по ней
    уже существуют результаты.
    """

    __tablename__ = "assessment_objective_results"

    __table_args__ = (
        UniqueConstraint(
            "assessment_result_id",
            "assessment_objective_id",
            name="uq_assessment_objective_result",
        ),
        CheckConstraint(
            "score >= 0",
            name="ck_assessment_objective_results_score_non_negative",
        ),
        CheckConstraint(
            "max_score > 0",
            name="ck_assessment_objective_results_max_score_positive",
        ),
        CheckConstraint(
            "score <= max_score",
            name="ck_assessment_objective_results_score_max",
        ),
        CheckConstraint(
            "percent >= 0 AND percent <= 100",
            name="ck_assessment_objective_results_percent_range",
        ),
        Index(
            "ix_assessment_objective_results_objective",
            "assessment_objective_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    assessment_result_id: Mapped[int] = mapped_column(
        ForeignKey(
            "assessment_results.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    assessment_objective_id: Mapped[int] = mapped_column(
        ForeignKey(
            "assessment_objectives.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    score: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    max_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    percent: Mapped[Decimal] = mapped_column(
        Numeric(7, 4),
        nullable=False,
    )

    assessment_result: Mapped[AssessmentResult] = relationship(
        "AssessmentResult",
        back_populates="objective_results",
        lazy="raise",
    )

    assessment_objective: Mapped[
        AssessmentObjective
    ] = relationship(
        "AssessmentObjective",
        back_populates="objective_results",
        lazy="raise",
    )


# =========================================================
# QUESTION
# =========================================================


class AssessmentQuestion(Base):
    """
    Задание онлайн Assessment.

    content, answer_key и grading_settings используют JSONB:
    структура зависит от question_type и может расширяться
    без новой миграции для каждого типа задания.
    """

    __tablename__ = "assessment_questions"

    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "order_no",
            name="uq_assessment_question_order",
        ),
        CheckConstraint(
            "max_score > 0",
            name="ck_assessment_questions_max_score_positive",
        ),
        CheckConstraint(
            "order_no > 0",
            name="ck_assessment_questions_order_positive",
        ),
        Index(
            "ix_assessment_questions_objective",
            "assessment_objective_id",
        ),
        Index(
            "ix_assessment_questions_type",
            "question_type",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    assessment_id: Mapped[int] = mapped_column(
        ForeignKey(
            "assessments.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    assessment_objective_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "assessment_objectives.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    question_type: Mapped[AssessmentQuestionType] = mapped_column(
        ASSESSMENT_QUESTION_TYPE_ENUM,
        nullable=False,
    )

    # Immutable rich condition, explanation and multiple-objective bindings.
    diagnostic_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    instruction: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    max_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    order_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa_text("'{}'::jsonb"),
    )

    answer_key: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa_text("'{}'::jsonb"),
    )

    grading_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa_text("'{}'::jsonb"),
    )

    is_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sa_text("true"),
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sa_text("true"),
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

    assessment: Mapped[Assessment] = relationship(
        "Assessment",
        back_populates="questions",
        lazy="raise",
    )

    assessment_objective: Mapped[
        AssessmentObjective | None
        ] = relationship(
        "AssessmentObjective",
        back_populates="questions",
        lazy="raise",
    )

    student_answers: Mapped[
        list[AssessmentStudentAnswer]
    ] = relationship(
        "AssessmentStudentAnswer",
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )


# =========================================================
# STUDENT ANSWER
# =========================================================


class AssessmentStudentAnswer(Base):
    """
    Ответ ученика на конкретное задание.

    answer_data хранит форму ответа в JSONB.
    """

    __tablename__ = "assessment_student_answers"

    __table_args__ = (
        UniqueConstraint(
            "assessment_student_id",
            "question_id",
            name="uq_assessment_student_answer",
        ),
        CheckConstraint(
            "score IS NULL OR score >= 0",
            name="ck_assessment_student_answers_score_non_negative",
        ),
        CheckConstraint(
            "max_score > 0",
            name="ck_assessment_student_answers_max_score_positive",
        ),
        CheckConstraint(
            "score IS NULL OR score <= max_score",
            name="ck_assessment_student_answers_score_max",
        ),
        Index(
            "ix_assessment_student_answers_status",
            "status",
        ),
        Index(
            "ix_assessment_student_answers_question",
            "question_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    assessment_student_id: Mapped[int] = mapped_column(
        ForeignKey(
            "assessment_students.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    question_id: Mapped[int] = mapped_column(
        ForeignKey(
            "assessment_questions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    answer_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa_text("'{}'::jsonb"),
    )

    score: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    max_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    status: Mapped[AssessmentAnswerStatus] = mapped_column(
        ASSESSMENT_ANSWER_STATUS_ENUM,
        nullable=False,
        default=AssessmentAnswerStatus.NOT_ANSWERED,
    )

    is_correct: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    checked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    assessment_student: Mapped[
        AssessmentStudent
    ] = relationship(
        "AssessmentStudent",
        back_populates="answers",
        lazy="raise",
    )

    question: Mapped[AssessmentQuestion] = relationship(
        "AssessmentQuestion",
        back_populates="student_answers",
        lazy="raise",
    )

    checked_by_user: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[checked_by_user_id],
        lazy="raise",
    )


# =========================================================
# ASSESSMENT ↔ VSHK TASK
# =========================================================


class AssessmentTaskLink(Base):
    """
    Связь Assessment с задачей месячного плана ВШК.

    Assessment остается самостоятельным объектом.
    При создании связи сервис обязан проверить принадлежность
    задачи и Assessment одной школе.
    """

    __tablename__ = "assessment_task_links"

    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "month_item_id",
            name="uq_assessment_task_link",
        ),
        Index(
            "ix_assessment_task_links_month_item",
            "month_item_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    assessment_id: Mapped[int] = mapped_column(
        ForeignKey(
            "assessments.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    month_item_id: Mapped[int] = mapped_column(
        ForeignKey(
            "school_month_plan_items.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    link_type: Mapped[AssessmentTaskLinkType] = mapped_column(
        ASSESSMENT_TASK_LINK_TYPE_ENUM,
        nullable=False,
        default=AssessmentTaskLinkType.PRIMARY,
    )

    linked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    assessment: Mapped[Assessment] = relationship(
        "Assessment",
        back_populates="task_links",
        lazy="raise",
    )

    month_item: Mapped[SchoolMonthPlanItem] = relationship(
        "SchoolMonthPlanItem",
        lazy="raise",
    )

    linked_by_user: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[linked_by_user_id],
        lazy="raise",
    )


class AssessmentQualitySummary(Base):
    """
    Агрегированный аналитический snapshot качества знаний
    по одной AssessmentGroup.

    Одна строка = один класс внутри одного Assessment.

    Создаётся при завершении Assessment и после этого
    используется для быстрой аналитики:
        - по классу;
        - по школе;
        - по району;
        - по области;
        - по предмету;
        - по параллели;
        - по учебному году.

    Исходные AssessmentResult остаются source of truth.
    Summary является оптимизированной read-model.
    """

    __tablename__ = "assessment_quality_summaries"

    __table_args__ = (
        # Один summary на одну AssessmentGroup.
        UniqueConstraint(
            "assessment_group_id",
            name="uq_assessment_quality_summary_group",
        ),

        # Защита границы школы:
        # Assessment и summary принадлежат одной школе.
        ForeignKeyConstraint(
            ["assessment_id", "school_id"],
            [
                "assessments.id",
                "assessments.school_id",
            ],
            name="fk_assessment_quality_summary_assessment_school",
            ondelete="CASCADE",
        ),

        # AssessmentGroup и summary принадлежат одной школе.
        ForeignKeyConstraint(
            ["assessment_group_id", "school_id"],
            [
                "assessment_groups.id",
                "assessment_groups.school_id",
            ],
            name="fk_assessment_quality_summary_group_school",
            ondelete="CASCADE",
        ),

        # -------------------------------------------------
        # DIRECT LOOKUPS
        # -------------------------------------------------

        Index(
            "ix_assessment_quality_summaries_assessment",
            "assessment_id",
        ),

        Index(
            "ix_assessment_quality_summaries_school_class",
            "school_class_id",
        ),

        # -------------------------------------------------
        # SCHOOL ANALYTICS
        # -------------------------------------------------

        Index(
            "ix_assessment_quality_summaries_teacher_analytics",
            "school_id",
            "teacher_staff_member_id_snapshot",
            "academic_year_start_snapshot",
            "subject_id",
            "grade_level_snapshot",
        ),

        Index(
            "ix_assessment_quality_school_year_subject_grade",
            "school_id",
            "academic_year_start_snapshot",
            "subject_id",
            "grade_level_snapshot",
        ),

        # -------------------------------------------------
        # DISTRICT ANALYTICS
        # -------------------------------------------------

        Index(
            "ix_assessment_quality_district_year_subject_grade",
            "district_id_snapshot",
            "academic_year_start_snapshot",
            "subject_id",
            "grade_level_snapshot",
        ),

        # -------------------------------------------------
        # REGION ANALYTICS
        # -------------------------------------------------

        Index(
            "ix_assessment_quality_region_year_subject_grade",
            "region_id_snapshot",
            "academic_year_start_snapshot",
            "subject_id",
            "grade_level_snapshot",
        ),

        # -------------------------------------------------
        # KNOWLEDGE QUALITY DYNAMICS
        # -------------------------------------------------

        Index(
            "ix_assessment_quality_school_dynamics",
            "school_id",
            "academic_year_start_snapshot",
            "subject_id",
            "grade_level_snapshot",
            "checkpoint_snapshot",
        ),

        Index(
            "ix_assessment_quality_district_dynamics",
            "district_id_snapshot",
            "academic_year_start_snapshot",
            "subject_id",
            "grade_level_snapshot",
            "checkpoint_snapshot",
        ),

        Index(
            "ix_assessment_quality_region_dynamics",
            "region_id_snapshot",
            "academic_year_start_snapshot",
            "subject_id",
            "grade_level_snapshot",
            "checkpoint_snapshot",
        ),
    )

    # =====================================================
    # IDENTITY
    # =====================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey(
            "schools.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    assessment_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    assessment_group_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    school_class_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    subject_id: Mapped[int] = mapped_column(
        ForeignKey(
            "subjects.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    # =====================================================
    # ORGANIZATION SNAPSHOT
    # =====================================================

    teacher_staff_member_id_snapshot: Mapped[
        int | None
        ] = mapped_column(
        Integer,
        nullable=True,
    )

    teacher_name_snapshot: Mapped[
        str | None
        ] = mapped_column(
        String(255),
        nullable=True,
    )

    district_id_snapshot: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    region_id_snapshot: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # =====================================================
    # CLASS / PERIOD SNAPSHOT
    # =====================================================

    class_name_snapshot: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    grade_level_snapshot: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    academic_year_start_snapshot: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    checkpoint_snapshot: Mapped[AssessmentCheckpoint | None] = mapped_column(
        ASSESSMENT_CHECKPOINT_ENUM,
        nullable=True,
    )

    # =====================================================
    # PARTICIPATION
    # =====================================================

    total_students: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    participated_students: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    absent_students: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    excused_students: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    not_completed_students: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # =====================================================
    # GRADES
    # =====================================================

    grade_5_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    grade_4_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    grade_3_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    grade_2_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # =====================================================
    # AGGREGATE VALUES
    # =====================================================

    """
    Эти суммы нужны для корректного weighted aggregation
    на уровне школы / района / области.

    Нельзя усреднять average классов напрямую.
    """

    score_sum: Mapped[Decimal] = mapped_column(
        Numeric(
            14,
            4,
        ),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )

    percent_sum: Mapped[Decimal] = mapped_column(
        Numeric(
            16,
            4,
        ),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )

    # =====================================================
    # PRECALCULATED INDICATORS
    # =====================================================

    average_score: Mapped[Decimal | None] = mapped_column(
        Numeric(
            10,
            2,
        ),
        nullable=True,
    )

    average_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(
            7,
            2,
        ),
        nullable=True,
    )

    achievement_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(
            7,
            2,
        ),
        nullable=True,
    )

    quality_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(
            7,
            2,
        ),
        nullable=True,
    )

    # =====================================================
    # AUDIT
    # =====================================================

    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
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

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    assessment: Mapped["Assessment"] = relationship(
        "Assessment",
        primaryjoin=(
            "AssessmentQualitySummary.assessment_id "
            "== Assessment.id"
        ),
        foreign_keys=[
            assessment_id,
        ],
        lazy="raise",
    )

    assessment_group: Mapped["AssessmentGroup"] = relationship(
        "AssessmentGroup",
        primaryjoin=(
            "AssessmentQualitySummary.assessment_group_id "
            "== AssessmentGroup.id"
        ),
        foreign_keys=[
            assessment_group_id,
        ],
        lazy="raise",
    )

    subject: Mapped["Subject"] = relationship(
        "Subject",
        foreign_keys=[
            subject_id,
        ],
        lazy="raise",
    )


# =========================================================
# ASSESSMENT CAMPAIGN
# =========================================================


class AssessmentCampaign(Base):
    """
    Кампания Assessment.

    Используется для объединения нескольких
    самостоятельных однопредметных Assessment
    в одно организационное мероприятие.

    Пример:

        "9-сынып нөлдік бақылау"

        ├── Информатика
        ├── Математика
        ├── Қазақ тілі
        └── Ағылшын тілі

    Каждый дочерний Assessment остаётся
    самостоятельным однопредметным объектом.

    campaign не хранит предмет,
    max_score или результаты учеников.

    Эти данные принадлежат конкретным Assessment.
    """

    __tablename__ = "assessment_campaigns"

    __table_args__ = (
        # -------------------------------------------------
        # Нужен как целевой уникальный ключ
        # для составного FK:
        #
        # Assessment(
        #     campaign_id,
        #     school_id
        # )
        #     ->
        # AssessmentCampaign(
        #     id,
        #     school_id
        # )
        # -------------------------------------------------

        UniqueConstraint(
            "id",
            "school_id",
            name="uq_assessment_campaigns_id_school",
        ),

        # -------------------------------------------------
        # ANALYTICS / LOOKUPS
        # -------------------------------------------------

        Index(
            "ix_assessment_campaigns_school_year",
            "school_id",
            "academic_year_start",
        ),

        Index(
            "ix_assessment_campaigns_school_created",
            "school_id",
            "created_at",
        ),
    )

    # =====================================================
    # IDENTITY
    # =====================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey(
            "schools.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    created_by_user_id: Mapped[
        int | None
        ] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    # =====================================================
    # CONTENT
    # =====================================================

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[
        str | None
        ] = mapped_column(
        Text,
        nullable=True,
    )

    # =====================================================
    # PERIOD
    # =====================================================

    academic_year_start: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    scheduled_at: Mapped[
        datetime | None
        ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # =====================================================
    # AUDIT
    # =====================================================

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

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    school: Mapped["School"] = relationship(
        "School",
        lazy="raise",
    )

    created_by_user: Mapped[
        "User | None"
    ] = relationship(
        "User",
        foreign_keys=[
            created_by_user_id,
        ],
        lazy="raise",
    )

    assessments: Mapped[
        list["Assessment"]
    ] = relationship(
        "Assessment",

        primaryjoin=lambda: and_(
            AssessmentCampaign.id
            == foreign(
                Assessment.campaign_id
            ),

            AssessmentCampaign.school_id
            == Assessment.school_id,
        ),

        foreign_keys=lambda: [
            Assessment.campaign_id,
        ],

        back_populates="campaign",

        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<AssessmentCampaign "
            f"id={self.id} "
            f"school_id={self.school_id} "
            f"title={self.title!r}>"
        )


class QuestionBankItem(Base):
    """
    Переиспользуемое задание банка вопросов.

    QuestionBankItem является исходным заданием.
    При формировании конкретного Assessment его данные
    копируются в AssessmentQuestion.

    Изменение QuestionBankItem не должно изменять уже
    созданные AssessmentQuestion.
    """

    __tablename__ = "question_bank_items"

    requires_bilingual: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa_text("false"),
    )

    quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint("quarter IS NULL OR quarter BETWEEN 1 AND 4", name="ck_qb_item_quarter"),
        CheckConstraint(
            "grade_level BETWEEN 1 AND 12",
            name="ck_question_bank_items_grade_level",
        ),
        CheckConstraint(
            "max_score > 0",
            name="ck_question_bank_items_max_score_positive",
        ),
        Index(
            "ix_question_bank_items_lookup",
            "subject_id",
            "grade_level",
            "language",
            "status",
        ),
    )
    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    subject_id: Mapped[int] = mapped_column(
        ForeignKey(
            "subjects.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    grade_level: Mapped[int] = mapped_column(
        nullable=False,
        index=True,
    )

    question_type: Mapped[
        AssessmentQuestionType
    ] = mapped_column(
        ASSESSMENT_QUESTION_TYPE_ENUM,
        nullable=False,
        index=True,
    )

    difficulty: Mapped[
        AssessmentQuestionDifficulty
    ] = mapped_column(
        ASSESSMENT_QUESTION_DIFFICULTY_ENUM,
        nullable=False,
        index=True,
    )

    language: Mapped[
        AssessmentLanguage
    ] = mapped_column(
        ASSESSMENT_LANGUAGE_ENUM,
        nullable=False,
        index=True,
    )

    status: Mapped[
        QuestionBankItemStatus
    ] = mapped_column(
        QUESTION_BANK_ITEM_STATUS_ENUM,
        nullable=False,
        default=QuestionBankItemStatus.DRAFT,
        index=True,
    )

    origin: Mapped[
        QuestionBankItemOrigin
    ] = mapped_column(
        QUESTION_BANK_ITEM_ORIGIN_ENUM,
        nullable=False,
        default=QuestionBankItemOrigin.MANUAL,
        index=True,
    )

    title: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    text_segments: Mapped[
        list[dict[str, Any]]
    ] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sa_text("'[]'::jsonb"),
    )

    instruction: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa_text("'{}'::jsonb"),
    )
    answer_key: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa_text("'{}'::jsonb"),
    )

    grading_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa_text("'{}'::jsonb"),
    )

    max_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    explanation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    author_comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    subject: Mapped["Subject"] = relationship(
        "Subject",
        back_populates="question_bank_items",
        lazy="raise",
    )

    created_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[created_by_user_id],
        lazy="raise",
    )

    objectives: Mapped[
        list["QuestionBankItemObjective"]
    ] = relationship(
        "QuestionBankItemObjective",
        back_populates="question_bank_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
        order_by="QuestionBankItemObjective.order_no",
    )

    reviews: Mapped[list["QuestionBankItemReview"]] = relationship(
        "QuestionBankItemReview",
        back_populates="question_bank_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
        order_by=(
            "QuestionBankItemReview.created_at.desc()"
        ),
    )


class QuestionBankItemObjective(Base):
    """
    Связь задания банка вопросов
    с учебной целью.

    Одно задание может проверять несколько
    LearningObjective.
    """

    __tablename__ = "question_bank_item_objectives"

    __table_args__ = (
        UniqueConstraint(
            "question_bank_item_id",
            "learning_objective_id",
            name="uq_question_bank_item_objective_learning",
        ),
        UniqueConstraint(
            "question_bank_item_id",
            "order_no",
            name="uq_question_bank_item_objective_order",
        ),
        CheckConstraint(
            "order_no > 0",
            name="ck_question_bank_item_objective_order_positive",
        ),
    )
    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    question_bank_item_id: Mapped[int] = mapped_column(
        ForeignKey(
            "question_bank_items.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    learning_objective_id: Mapped[int] = mapped_column(
        ForeignKey(
            "learning_objectives.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    order_no: Mapped[int] = mapped_column(
        nullable=False,
    )

    question_bank_item: Mapped[
        "QuestionBankItem"
    ] = relationship(
        "QuestionBankItem",
        back_populates="objectives",
        lazy="raise",
    )

    learning_objective: Mapped[
        "LearningObjective"
    ] = relationship(
        "LearningObjective",
        back_populates="question_bank_item_objectives",
        lazy="raise",
    )


# =========================================================
# QUESTION BANK ITEM REVIEW
# =========================================================


class QuestionBankItemReview(Base):
    """
    Исторический результат экспертной проверки
    QuestionBankItem человеком.

    Review не заменяет QuestionBankItem.status.

    Решение APPROVED соответствует переходу:

        REVIEW -> READY

    Решение REJECTED соответствует переходу:

        REVIEW -> REJECTED

    Один QuestionBankItem может проходить экспертную
    проверку несколько раз в течение жизненного цикла.
    """

    __tablename__ = "question_bank_item_reviews"

    __table_args__ = (
        Index(
            "ix_question_bank_item_reviews_item",
            "question_bank_item_id",
        ),
        Index(
            "ix_question_bank_item_reviews_reviewer",
            "reviewer_user_id",
        ),
        Index(
            "ix_question_bank_item_reviews_created",
            "created_at",
        ),
    )

    # =====================================================
    # IDENTITY
    # =====================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    question_bank_item_id: Mapped[int] = mapped_column(
        ForeignKey(
            "question_bank_items.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    # =====================================================
    # REVIEW
    # =====================================================

    reviewer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    decision: Mapped[
        QuestionBankReviewDecision
    ] = mapped_column(
        QUESTION_BANK_REVIEW_DECISION_ENUM,
        nullable=False,
    )

    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # =====================================================
    # AUDIT
    # =====================================================

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    question_bank_item: Mapped[
        "QuestionBankItem"
    ] = relationship(
        "QuestionBankItem",
        back_populates="reviews",
        lazy="raise",
    )

    reviewer_user: Mapped[
        "User | None"
    ] = relationship(
        "User",
        foreign_keys=[reviewer_user_id],
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<QuestionBankItemReview "
            f"id={self.id} "
            f"question_bank_item_id="
            f"{self.question_bank_item_id} "
            f"reviewer_user_id="
            f"{self.reviewer_user_id} "
            f"decision={self.decision.value!r}>"
        )


class AIQuestionGenerationRun(Base):
    """
    Один запуск AI-генерации вопросов
    для AssessmentBlueprint.

    Run фиксирует жизненный цикл внешней AI-операции:

        RUNNING
            ↓
        COMPLETED

    либо:

        RUNNING
            ↓
        FAILED

    Модель используется для:
        - защиты от параллельных генераций;
        - контроля повторных платных AI-вызовов;
        - истории запусков;
        - будущего audit AI generation.

    Сам generated content здесь не хранится.
    QuestionBankItem остаётся отдельной сущностью.
    """

    __tablename__ = "ai_question_generation_runs"

    __table_args__ = (
        CheckConstraint(
            "question_count > 0",
            name=(
                "ck_ai_question_generation_runs_"
                "question_count_positive"
            ),
        ),
        Index(
            "ix_ai_question_generation_runs_blueprint",
            "blueprint_id",
        ),
        Index(
            "ix_ai_question_generation_runs_status",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    # =====================================================
    # BLUEPRINT
    # =====================================================

    blueprint_id: Mapped[int] = mapped_column(
        ForeignKey(
            "assessment_blueprints.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    # =====================================================
    # GENERATION STATE
    # =====================================================

    status: Mapped[
        AIQuestionGenerationRunStatus
    ] = mapped_column(
        AI_QUESTION_GENERATION_RUN_STATUS_ENUM,
        nullable=False,
        default=AIQuestionGenerationRunStatus.RUNNING,
    )

    question_count: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    # =====================================================
    # FAILURE
    # =====================================================

    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # =====================================================
    # AUDIT
    # =====================================================

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    blueprint: Mapped[
        "AssessmentBlueprint"
    ] = relationship(
        "AssessmentBlueprint",
        back_populates="ai_generation_runs",
        lazy="raise",
    )

    created_by_user: Mapped[
        "User | None"
    ] = relationship(
        "User",
        foreign_keys=[created_by_user_id],
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<AIQuestionGenerationRun "
            f"id={self.id} "
            f"blueprint_id={self.blueprint_id} "
            f"status={self.status.value!r}>"
        )


class QuestionBankLanguageVariant(Base):
    """Second language of one task; lifecycle and reviews belong to QuestionBankItem."""
    __tablename__ = "question_bank_language_variants"
    __table_args__ = (CheckConstraint("language IN ('ru','kk')", name="ck_qb_variant_language"),)
    item_id: Mapped[int] = mapped_column(ForeignKey("question_bank_items.id", ondelete="CASCADE"), primary_key=True)
    language: Mapped[str] = mapped_column(String(2), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    edited_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class QuestionBankTranslationRequest(Base):
    """Durable AI proposal; it never owns the task's review status."""
    __tablename__ = 'qb_translation_requests'
    __table_args__ = (
        CheckConstraint("status IN ('running','proposed','failed')", name='ck_qb_translation_status'),
        CheckConstraint("language IN ('ru','kk')", name='ck_qb_translation_language'),
    )
    item_id: Mapped[int] = mapped_column(ForeignKey('question_bank_items.id', ondelete='CASCADE'), primary_key=True)
    source_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    language: Mapped[str] = mapped_column(String(2), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    attempt_token: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    values_json: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class QuestionBankManualCreationSet(Base):
    __tablename__ = 'qb_manual_creation_sets'
    __table_args__ = (Index('ix_qb_manual_sets_user_created','user_id','created_at'),)
    token: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False)
    slots: Mapped[list] = mapped_column(JSONB, nullable=False)
    item_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
