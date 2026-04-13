# app/modules/org/models_documents.py (Таблицы)

from __future__ import annotations

from typing import TYPE_CHECKING
from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.planning.models_school import SchoolPlan
    from app.modules.staff.models_staff_school import SchoolStaffMember, SchoolStaffRole


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
