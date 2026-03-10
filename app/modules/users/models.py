# app/modules/users/models.py

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Integer,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import USER_ROLE_ENUM
from app.modules.users.enums import UserRole


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            """
            (
                (CASE WHEN region_id IS NULL THEN 0 ELSE 1 END) +
                (CASE WHEN district_id IS NULL THEN 0 ELSE 1 END) +
                (CASE WHEN school_id IS NULL THEN 0 ELSE 1 END)
            ) <= 1
            """,
            name="ck_users_single_scope",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    iin: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)

    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(USER_ROLE_ENUM, nullable=False, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)

    otp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    eds_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    school_id: Mapped[int | None] = mapped_column(
        ForeignKey("schools.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    staff_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("school_staff_members.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
        index=True,
    )

    region: Mapped["Region | None"] = relationship("Region")
    district: Mapped["District | None"] = relationship("District")
    school: Mapped["School | None"] = relationship("School")

    staff_member: Mapped["SchoolStaffMember | None"] = relationship(
        "SchoolStaffMember",
        foreign_keys=[staff_member_id],
        back_populates="user_account",
        uselist=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username} role={self.role}>"


class RegistrationCode(Base):
    __tablename__ = "registration_codes"

    __table_args__ = (
        # максимум 1 scope: region OR district OR school OR none
        CheckConstraint(
            """
            (
                (CASE WHEN region_id IS NULL THEN 0 ELSE 1 END) +
                (CASE WHEN district_id IS NULL THEN 0 ELSE 1 END) +
                (CASE WHEN school_id IS NULL THEN 0 ELSE 1 END)
            ) <= 1
            """,
            name="ck_codes_single_scope",
        ),
        Index("ix_registration_codes_issued_by", "issued_by_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # детерминированный хэш для поиска по введенному коду (sha256 hex = 64)
    code_lookup_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    # роль, которую можно СОЗДАТЬ по коду
    target_role: Mapped[UserRole] = mapped_column(USER_ROLE_ENUM, nullable=False)

    # scope кода
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    school_id: Mapped[int | None] = mapped_column(
        ForeignKey("schools.id", ondelete="RESTRICT"),
        nullable=True,
    )

    issued_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    quota_total: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    quota_left: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    issued_by: Mapped["User"] = relationship("User", foreign_keys=[issued_by_user_id])
    revoked_by: Mapped["User | None"] = relationship("User", foreign_keys=[revoked_by_user_id])

    uses: Mapped[list["RegistrationCodeUse"]] = relationship(
        back_populates="code_obj",
        cascade="all, delete-orphan",
    )


class RegistrationCodeUse(Base):
    __tablename__ = "registration_code_uses"

    __table_args__ = (
        Index("ix_code_uses_code_id", "code_id"),
        Index("ix_code_uses_used_by", "used_by_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    code_id: Mapped[int] = mapped_column(
        ForeignKey("registration_codes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    used_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    code_obj: Mapped["RegistrationCode"] = relationship("RegistrationCode", back_populates="uses")
    used_by: Mapped["User"] = relationship("User", foreign_keys=[used_by_user_id])
