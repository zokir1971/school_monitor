# app/modules/staff/models_staff_school.py

from datetime import date

from sqlalchemy import ForeignKey, UniqueConstraint, Boolean, Index
from sqlalchemy import Text, String, Integer, Date, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import RESPONSIBLE_ROLE_ENUM
from app.modules.planning.enums import ResponsibleRole

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.org.models import School
    from app.modules.planning.models_school import SchoolPlanRow11Assignee
    from app.modules.planning.models_month_plan import SchoolMonthPlanItemAssignee


class SchoolStaffMember(Base):
    __tablename__ = "school_staff_members"
    __table_args__ = (
        # ИИН обычно уникален по стране, но можно сделать уникальность в рамках школы:
        UniqueConstraint("school_id", "iin", name="uq_staff_school_iin"),
        Index("ix_staff_school_id", "school_id"),
        Index("ix_staff_iin", "iin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # базовые
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    iin: Mapped[str] = mapped_column(String(12), nullable=False)  # 12 цифр

    # твоя “табличка”
    education: Mapped[str | None] = mapped_column(Text, nullable=True)  # образование
    academic_degree: Mapped[str | None] = mapped_column(String(255), nullable=True)  # академическая степень
    position_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # должность (как в документе)
    university: Mapped[str | None] = mapped_column(Text, nullable=True)  # ВУЗ
    graduation_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # когда окончил
    diploma_no: Mapped[str | None] = mapped_column(String(64), nullable=True)  # диплом №
    diploma_specialty: Mapped[str | None] = mapped_column(Text, nullable=True)  # специальность по диплому
    study_type: Mapped[str | None] = mapped_column(Text, nullable=True)  # вид обучение
    affiliation: Mapped[str | None] = mapped_column(Text, nullable=True)  # принадлежность

    # стаж
    ped_start_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)  # педстаж начало
    total_experience_years: Mapped[int | None] = mapped_column(Integer,
                                                               nullable=True)  # общий стаж (если хранишь годами)
    ped_experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)  # пед стаж

    qualification_category: Mapped[str | None] = mapped_column(Text, nullable=True)  # квалиф. категория
    qualification_order_no: Mapped[str | None] = mapped_column(String(64), nullable=True)  # приказ квалиф. категория
    qualification_order_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)  # дата приказа
    attestation_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # когда аттестация
    reattestation_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # когда переаттестация

    course_passed_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # қашан курстан өткені
    course_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # курстан қашан өтеді
    course_place: Mapped[str | None] = mapped_column(Text, nullable=True)  # где прошел курсы
    course_certificate_no: Mapped[str | None] = mapped_column(String(64), nullable=True)  # сертификат курсов

    subject: Mapped[str | None] = mapped_column(Text, nullable=True)  # какой предмет преподает
    awards: Mapped[str | None] = mapped_column(Text, nullable=True)  # награды
    creative_topic: Mapped[str | None] = mapped_column(Text, nullable=True)  # тема творческой работы

    rating: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)  # рейтинг (если нужен)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    # future: если потом появится user аккаунт
    user_account: Mapped["User | None"] = relationship(
        "User",
        foreign_keys="User.staff_member_id",
        back_populates="staff_member",
        uselist=False,
    )

    school: Mapped["School"] = relationship(
        "School",
        back_populates="staff_members",
        lazy="selectin",
    )

    roles = relationship(
        "SchoolStaffRole",
        back_populates="staff_member",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    assigned_rows11: Mapped[list["SchoolPlanRow11Assignee"]] = relationship(
        "SchoolPlanRow11Assignee",
        back_populates="staff_member",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


# =========================================================
# SchoolStaffRole (персонал школы: кто в какой должности)
# =========================================================
class SchoolStaffRole(Base):
    __tablename__ = "school_staff_roles"

    id: Mapped[int] = mapped_column(primary_key=True)

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
    )

    staff_member_id: Mapped[int] = mapped_column(
        ForeignKey("school_staff_members.id", ondelete="CASCADE"),
        nullable=False,
    )

    role: Mapped[ResponsibleRole] = mapped_column(RESPONSIBLE_ROLE_ENUM, nullable=False)

    role_context: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ЭТО ОБЯЗАТЕЛЬНО
    school: Mapped["School"] = relationship(
        "School",
        back_populates="staff_roles",
        lazy="selectin",
    )

    staff_member: Mapped["SchoolStaffMember"] = relationship(
        "SchoolStaffMember",
        back_populates="roles",
        lazy="selectin",
    )

    month_task_assignments: Mapped[list["SchoolMonthPlanItemAssignee"]] = relationship(
        "SchoolMonthPlanItemAssignee",
        back_populates="staff_role",
        lazy="selectin",
    )
