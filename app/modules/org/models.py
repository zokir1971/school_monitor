# app/modules/org/models.py (Таблицы справочник регион, район, организация образования)

from __future__ import annotations

from typing import TYPE_CHECKING
from datetime import datetime
from sqlalchemy import DateTime
from app.common.time import utcnow
from sqlalchemy import String, ForeignKey, UniqueConstraint, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.planning.models_school import SchoolPlan
    from app.modules.staff.models_staff_school import SchoolStaffMember, SchoolStaffRole
    from app.modules.assessment.models_question_bank_experts import QuestionBankExpert


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(primary_key=True)

    # область уникальна по названию
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    districts: Mapped[list["District"]] = relationship(
        "District",
        back_populates="region",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Region id={self.id} name={self.name}>"


class District(Base):
    __tablename__ = "districts"

    __table_args__ = (
        # район уникален в пределах области
        UniqueConstraint("region_id", "name", name="uq_district_region_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # индекс обязателен: почти все выборки будут по области
    region_id: Mapped[int] = mapped_column(
        ForeignKey("regions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    region: Mapped["Region"] = relationship(
        "Region",
        back_populates="districts",
        lazy="selectin",
    )

    schools: Mapped[list["School"]] = relationship(
        "School",
        back_populates="district",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<District id={self.id} name={self.name} region_id={self.region_id}>"


class School(Base):
    __tablename__ = "schools"

    __table_args__ = (
        # школа уникальна в пределах района
        UniqueConstraint("district_id", "name", name="uq_school_district_name"),
        CheckConstraint("governance_level IN ('district', 'region')", name="ck_school_governance_level"),
        Index("ix_school_governance_district", "governance_level", "district_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # индекс обязателен: почти все выборки будут по району
    district_id: Mapped[int] = mapped_column(
        ForeignKey("districts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Administrative authority; district_id continues to describe location.
    governance_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="district", server_default="district",
    )
    settlement: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    district: Mapped["District"] = relationship(
        "District",
        back_populates="schools",
        lazy="selectin",
    )

    vshk_plans: Mapped[list["SchoolPlan"]] = relationship(
        "SchoolPlan",
        back_populates="school",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    staff_members: Mapped[list["SchoolStaffMember"]] = relationship(
        "SchoolStaffMember",
        back_populates="school",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    staff_roles: Mapped[list["SchoolStaffRole"]] = relationship(
        "SchoolStaffRole",
        back_populates="school",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    question_bank_experts: Mapped[list["QuestionBankExpert"]] = relationship(
        "QuestionBankExpert",
        back_populates="school",
        lazy="raise",
    )


class SchoolGovernanceChange(Base):
    __tablename__ = "school_governance_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    old_level: Mapped[str] = mapped_column(String(16), nullable=False)
    new_level: Mapped[str] = mapped_column(String(16), nullable=False)
    old_district_id: Mapped[int] = mapped_column(nullable=False)
    new_district_id: Mapped[int] = mapped_column(nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
