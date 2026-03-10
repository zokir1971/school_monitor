# app/modules/planning/models.py
from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    Index,
    UniqueConstraint,
    func,
)
from typing import TYPE_CHECKING
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.planning.models_school import SchoolPlan, SchoolPlanRow4, SchoolPlanRow11


# =========================================================
# 1) Справочник направлений
# =========================================================
class PlanDirection(Base):
    __tablename__ = "plan_directions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    short_title: Mapped[str] = mapped_column(Text, nullable=False)
    full_title: Mapped[str | None] = mapped_column(Text, nullable=True)

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # связь: направление может использоваться во многих шаблонах
    # ВАЖНО: удаление direction -> каскад обеспечивается FK в PlanTemplateDirection (ondelete="CASCADE")
    template_directions: Mapped[list["PlanTemplateDirection"]] = relationship(
        "PlanTemplateDirection",
        back_populates="direction",
        passive_deletes=True,
        lazy="selectin",
    )

    # ✅ строки школьного плана (удобно для join, но не обязательно)
    school_rows4: Mapped[list["SchoolPlanRow4"]] = relationship(
        "SchoolPlanRow4",
        back_populates="direction",
    )
    school_rows11: Mapped[list["SchoolPlanRow11"]] = relationship(
        "SchoolPlanRow11",
        back_populates="direction",
    )

    __table_args__ = (
        # чтобы не плодить одинаковые направления
        UniqueConstraint("short_title", name="uq_plan_directions_short_title"),
        Index("ix_plan_directions_active_sort", "is_active", "sort_order"),
    )


# =========================================================
# 2) Шаблон годового плана ВШК (на учебный год)
# =========================================================
class PlanTemplate(Base):
    __tablename__ = "plan_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(Text, nullable=False)
    academic_year: Mapped[str | None] = mapped_column(Text, nullable=True)  # "2026-2027"

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # направления внутри шаблона
    template_directions: Mapped[list["PlanTemplateDirection"]] = relationship(
        "PlanTemplateDirection",
        back_populates="template",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="PlanTemplateDirection.sort_order",
    )

    # (опционально) планы школ, созданные на основе этого шаблона
    school_plans: Mapped[list["SchoolPlan"]] = relationship(
        "SchoolPlan",
        back_populates="template",
    )

    __table_args__ = (
        Index("ix_plan_templates_active_year", "is_active", "academic_year"),
    )


# =========================================================
# 3) Направление внутри конкретного шаблона
#    (template + direction)
# =========================================================
class PlanTemplateDirection(Base):
    __tablename__ = "plan_template_directions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    template_id: Mapped[int] = mapped_column(
        ForeignKey("plan_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ✅ ВАЖНО: CASCADE, чтобы можно было удалить направление и всё, что на него ссылается
    direction_id: Mapped[int] = mapped_column(
        ForeignKey("plan_directions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)

    title_override: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    template: Mapped["PlanTemplate"] = relationship(
        "PlanTemplate",
        back_populates="template_directions",
        lazy="selectin",
    )

    # ✅ back_populates чтобы ORM корректно знал двустороннюю связь
    direction: Mapped["PlanDirection"] = relationship(
        "PlanDirection",
        back_populates="template_directions",
        lazy="selectin",
    )

    rows4: Mapped[list["PlanTemplateRow4"]] = relationship(
        "PlanTemplateRow4",
        back_populates="template_direction",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="PlanTemplateRow4.row_order",
    )

    rows11: Mapped[list["PlanTemplateRow11"]] = relationship(
        "PlanTemplateRow11",
        back_populates="template_direction",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="PlanTemplateRow11.row_order",
    )

    __table_args__ = (
        UniqueConstraint("template_id", "direction_id", name="uq_tpl_direction"),
        Index("ix_tpldir_template_sort", "template_id", "sort_order"),
    )

    @property
    def title(self) -> str:
        return (self.title_override or "").strip() or self.direction.short_title


# =========================================================
# 4) Таблица 4 — объекты контроля (строки)
# =========================================================
class PlanTemplateRow4(Base):
    __tablename__ = "plan_template_rows_4"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    template_direction_id: Mapped[int] = mapped_column(
        ForeignKey("plan_template_directions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    row_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)

    no: Mapped[str | None] = mapped_column(Text, nullable=True)
    control_object: Mapped[str] = mapped_column(Text, nullable=False, default="")
    risk_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    template_direction: Mapped["PlanTemplateDirection"] = relationship(
        "PlanTemplateDirection",
        back_populates="rows4",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("template_direction_id", "row_order", name="uq_tpldir_row4_order"),
        Index("ix_row4_tpldir_order", "template_direction_id", "row_order"),
    )


# =========================================================
# 5) Таблица 11 — задачи (строки)
# =========================================================
class PlanTemplateRow11(Base):
    __tablename__ = "plan_template_rows_11"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    template_direction_id: Mapped[int] = mapped_column(
        ForeignKey("plan_template_directions.id", ondelete="CASCADE"),
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    template_direction: Mapped["PlanTemplateDirection"] = relationship(
        "PlanTemplateDirection",
        back_populates="rows11",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("template_direction_id", "row_order", name="uq_tpldir_row11_order"),
        Index("ix_row11_tpldir_order", "template_direction_id", "row_order"),
    )
