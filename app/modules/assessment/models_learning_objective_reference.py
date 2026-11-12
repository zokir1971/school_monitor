"""Reference extensions; legacy LearningObjective remains registered in models.py."""
from __future__ import annotations
from datetime import date, datetime
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date, DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.db.base import Base


class LearningObjectiveFormulation(Base):
    """Exact language-specific wording; all SQL access is through repositories."""
    __tablename__ = 'learning_objective_formulations'
    __table_args__ = (
        UniqueConstraint('learning_objective_id', 'language', 'content_key', name='uq_lo_formulation_content'),
        CheckConstraint("language IN ('kz','ru')", name='ck_lo_formulation_language'),
        Index('ix_lo_formulation_objective_language', 'learning_objective_id', 'language'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    learning_objective_id: Mapped[int] = mapped_column(ForeignKey('learning_objectives.id', ondelete='CASCADE'),
                                                       nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    content_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    segments: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    quarters: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    source_cells: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False)


class LearningObjectiveSource(Base):
    __tablename__ = 'learning_objective_sources'
    __table_args__ = (UniqueConstraint('document_key', name='uq_lo_sources_document_key'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_key: Mapped[str] = mapped_column(String(150), nullable=False)
    order_number: Mapped[str] = mapped_column(String(100), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    edition_date: Mapped[date] = mapped_column(Date, nullable=False)
    title_kz: Mapped[str] = mapped_column(Text, nullable=False)
    title_ru: Mapped[str | None] = mapped_column(Text)
    file_key_kz: Mapped[str | None] = mapped_column(Text)
    file_key_ru: Mapped[str | None] = mapped_column(Text)
    sha256_kz: Mapped[str | None] = mapped_column(String(64))
    sha256_ru: Mapped[str | None] = mapped_column(String(64))
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class LearningObjectiveProgram(Base):
    __tablename__ = 'learning_objective_programs'
    __table_args__ = (
        UniqueConstraint('subject_id', 'source_id', 'appendix_number', 'variant_key', name='uq_lo_programs_variant'),
        UniqueConstraint('id', 'subject_id', name='uq_lo_programs_id_subject'),
        CheckConstraint('grade_from BETWEEN 1 AND 12 AND grade_to BETWEEN grade_from AND 12',
                        name='ck_lo_programs_grades'),
        Index('ix_lo_programs_subject_active', 'subject_id', 'is_active'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey('subjects.id', ondelete='RESTRICT'), nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey('learning_objective_sources.id', ondelete='RESTRICT'),
                                           nullable=False)
    appendix_number: Mapped[str] = mapped_column(String(100), nullable=False)
    variant_key: Mapped[str] = mapped_column(String(150), nullable=False)
    title_kz: Mapped[str] = mapped_column(Text, nullable=False)
    title_ru: Mapped[str | None] = mapped_column(Text)
    grade_from: Mapped[int] = mapped_column(Integer, nullable=False)
    grade_to: Mapped[int] = mapped_column(Integer, nullable=False)
    education_track: Mapped[str | None] = mapped_column(String(100))
    instruction_language: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class LearningObjectiveQuarter(Base):
    __tablename__ = 'learning_objective_quarters'
    __table_args__ = (
        CheckConstraint('quarter BETWEEN 1 AND 4', name='ck_lo_quarters_quarter'),
        Index('ix_lo_quarters_quarter_objective', 'quarter', 'learning_objective_id'),
    )
    learning_objective_id: Mapped[int] = mapped_column(Integer, ForeignKey('learning_objectives.id',
                                                                           ondelete='CASCADE'), primary_key=True)
    quarter: Mapped[int] = mapped_column(Integer, primary_key=True)
