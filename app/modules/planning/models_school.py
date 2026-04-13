# app/modules/planning/models_school.py
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import PLAN_PERIOD_ENUM, RESPONSIBLE_ROLE_ENUM, REVIEW_PLACE_ENUM, DOCUMENT_TYPE_ENUM
from app.modules.planning.enums import PlanPeriodType, ResponsibleRole, ReviewPlace
from app.modules.reports.enums import DocumentType

if TYPE_CHECKING:
    from app.modules.org.models import School
    from app.modules.planning.models import PlanDirection, PlanTemplate
    from app.modules.planning.models_month_plan import SchoolMonthPlan, SchoolMonthPlanItem
    from app.modules.staff.models_staff_school import SchoolStaffMember
    from app.modules.reports.models_documents import TaskExecutionDocument


# =========================================================
# SchoolPlan (годовой план школы на основе шаблона)
# =========================================================
class SchoolPlan(Base):
    __tablename__ = "school_plans"
    __table_args__ = (
        # Обычно у школы один план на учебный год
        UniqueConstraint("school_id", "academic_year", name="uq_school_plans_school_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    template_id: Mapped[int] = mapped_column(
        ForeignKey("plan_templates.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    academic_year: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # "2026-2027"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ---------- relationships ----------
    school: Mapped["School"] = relationship(
        "School",
        back_populates="vshk_plans",  # добавить в School
        lazy="selectin",
    )

    template: Mapped["PlanTemplate"] = relationship(
        "PlanTemplate",
        lazy="selectin",
    )

    rows4: Mapped[list["SchoolPlanRow4"]] = relationship(
        "SchoolPlanRow4",
        back_populates="plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SchoolPlanRow4.direction_id.asc(), SchoolPlanRow4.row_order.asc(), SchoolPlanRow4.id.asc()",
        lazy="selectin",
    )

    rows11: Mapped[list["SchoolPlanRow11"]] = relationship(
        "SchoolPlanRow11",
        back_populates="plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SchoolPlanRow11.direction_id.asc(), SchoolPlanRow11.row_order.asc(), SchoolPlanRow11.id.asc()",
        lazy="selectin",
    )

    month_plans: Mapped[list["SchoolMonthPlan"]] = relationship(
        "SchoolMonthPlan",
        back_populates="school_plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


# =========================================================
# Row4 (таблица на 4 колонки)
# =========================================================
class SchoolPlanRow4(Base):
    __tablename__ = "school_plan_rows_4"
    __table_args__ = (
        # Внутри одного плана в одном направлении порядок должен быть уникальным
        UniqueConstraint("school_plan_id", "direction_id", "row_order", name="uq_school_rows4_plan_dir_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    school_plan_id: Mapped[int] = mapped_column(
        ForeignKey("school_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    direction_id: Mapped[int] = mapped_column(
        ForeignKey("plan_directions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    row_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)

    # колонки как в plan_template_rows_4
    no: Mapped[str | None] = mapped_column(Text, nullable=True)
    control_object: Mapped[str] = mapped_column(Text, nullable=False, default="")
    risk_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_custom: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )

    # Ответственные (роль + конкретный пользователь)
    responsible_role: Mapped[ResponsibleRole | None] = mapped_column(
        RESPONSIBLE_ROLE_ENUM,
        nullable=True,
        index=True,
    )

    responsible_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ---------- relationships ----------
    plan: Mapped["SchoolPlan"] = relationship(
        "SchoolPlan",
        back_populates="rows4",
        lazy="selectin",
    )

    direction: Mapped["PlanDirection"] = relationship(
        "PlanDirection",
        lazy="selectin",
    )

    responsible_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[responsible_user_id],
        lazy="selectin",
    )


# =========================================================
# Row11 (таблица на 11 колонок + период выполнения)
# =========================================================
class SchoolPlanRow11(Base):
    __tablename__ = "school_plan_rows_11"
    __table_args__ = (
        UniqueConstraint("school_plan_id", "direction_id", "row_order", name="uq_school_rows11_plan_dir_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    school_plan_id: Mapped[int] = mapped_column(
        ForeignKey("school_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    direction_id: Mapped[int] = mapped_column(
        ForeignKey("plan_directions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    row_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)

    topic: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    control_object: Mapped[str | None] = mapped_column(Text, nullable=True)
    control_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    methods: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadlines: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsibles: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_place: Mapped[str | None] = mapped_column(Text, nullable=True)
    management_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    second_control: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Период выполнения
    period_type: Mapped[PlanPeriodType] = mapped_column(
        PLAN_PERIOD_ENUM,
        nullable=False,
        default=PlanPeriodType.ALL_YEAR,
        index=True)
    period_value_int: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    period_values: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_custom: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )
    # ---------- relationships ----------
    plan: Mapped["SchoolPlan"] = relationship("SchoolPlan", back_populates="rows11", lazy="selectin")
    direction: Mapped["PlanDirection"] = relationship("PlanDirection", lazy="selectin")

    month_items: Mapped[list["SchoolMonthPlanItem"]] = relationship(
        "SchoolMonthPlanItem",
        back_populates="source_row11",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    role_assignments: Mapped[list["SchoolPlanRow11Responsible"]] = relationship(
        "SchoolPlanRow11Responsible",
        back_populates="row11",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    assignees: Mapped[list["SchoolPlanRow11Assignee"]] = relationship(
        "SchoolPlanRow11Assignee",
        back_populates="row11",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    required_documents: Mapped[list["SchoolPlanRow11RequiredDocument"]] = relationship(
        "SchoolPlanRow11RequiredDocument",
        back_populates="row11",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    review_places: Mapped[list["SchoolPlanRow11ReviewPlace"]] = relationship(
        "SchoolPlanRow11ReviewPlace",
        back_populates="row11",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


# Назначение задач по ролям (должностям)
class SchoolPlanRow11Responsible(Base):
    __tablename__ = "school_plan_row11_responsibles"
    __table_args__ = (
        # одна и та же роль не может быть назначена одной задаче дважды
        UniqueConstraint("row11_id", "role", name="uq_row11_role"),

        # индексы под отчёты/мониторинг
        Index("ix_row11_resp_row11_id", "row11_id"),
        Index("ix_row11_resp_role", "role"),
        Index("ix_row11_resp_row11_role", "row11_id", "role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    row11_id: Mapped[int] = mapped_column(
        ForeignKey("school_plan_rows_11.id", ondelete="CASCADE"),
        nullable=False,
    )

    role: Mapped[ResponsibleRole] = mapped_column(
        RESPONSIBLE_ROLE_ENUM,
        nullable=False,
    )

    # можно оставить (главный ответственный по должности)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    row11: Mapped["SchoolPlanRow11"] = relationship(
        "SchoolPlanRow11",
        back_populates="role_assignments",  # лучше так назвать в Row11
        lazy="selectin",
    )


# Персональное назначение на задачу должностного лица
class SchoolPlanRow11Assignee(Base):
    __tablename__ = "school_plan_row11_assignees"
    __table_args__ = (
        UniqueConstraint("row11_id", "staff_member_id", name="uq_row11_staff_member"),

        Index("ix_row11_assignee_row11_id", "row11_id"),
        Index("ix_row11_assignee_staff_member_id", "staff_member_id"),
        Index("ix_row11_assignee_staff_row11", "staff_member_id", "row11_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    row11_id: Mapped[int] = mapped_column(
        ForeignKey("school_plan_rows_11.id", ondelete="CASCADE"),
        nullable=False,
    )

    staff_member_id: Mapped[int] = mapped_column(
        ForeignKey("school_staff_members.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # кто назначил (удобно для аудита)
    assigned_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    row11: Mapped["SchoolPlanRow11"] = relationship(
        "SchoolPlanRow11",
        back_populates="assignees",
        lazy="selectin",
    )

    staff_member: Mapped["SchoolStaffMember"] = relationship(
        "SchoolStaffMember",
        back_populates="assigned_rows11",
        lazy="selectin",
    )

    assigned_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[assigned_by_user_id],
        lazy="selectin",
    )


class SchoolPlanRow11ReviewPlace(Base):
    __tablename__ = "school_plan_row_11_review_places"
    __table_args__ = (
        UniqueConstraint("row11_id", "review_place", name="uq_row11_review_place"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    row11_id: Mapped[int] = mapped_column(
        ForeignKey("school_plan_rows_11.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    review_place: Mapped[ReviewPlace] = mapped_column(
        REVIEW_PLACE_ENUM,
        nullable=False,
        index=True,
    )

    row11: Mapped["SchoolPlanRow11"] = relationship(
        "SchoolPlanRow11",
        back_populates="review_places",
    )


class SchoolPlanRow11RequiredDocument(Base):
    __tablename__ = "school_plan_row_11_required_documents"
    __table_args__ = (
        UniqueConstraint(
            "row11_id",
            "document_type",
            name="uq_row11_required_document_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    row11_id: Mapped[int] = mapped_column(
        ForeignKey("school_plan_rows_11.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    document_type: Mapped[DocumentType] = mapped_column(
        DOCUMENT_TYPE_ENUM,
        nullable=False,
        index=True,
    )

    row11: Mapped["SchoolPlanRow11"] = relationship(
        "SchoolPlanRow11",
        back_populates="required_documents",
    )

    task_execution_documents: Mapped[list["TaskExecutionDocument"]] = relationship(
        "TaskExecutionDocument",
        back_populates="required_document",
        lazy="selectin",
    )
