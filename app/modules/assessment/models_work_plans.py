"""Reusable work specifications; school-bound Assessment executions remain separate."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Any
from sqlalchemy import (
    Boolean,
    false,
    Integer,
    String,
    Text,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Index, DateTime,
    Numeric,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class AssessmentWorkPlan(Base):
    __tablename__ = 'assessment_work_plans'
    __table_args__ = (
        CheckConstraint("work_type IN ('baseline','sor','soch')", name='ck_work_plan_type'),
        CheckConstraint("input_mode IN ('manual','online')", name='ck_work_plan_input'),
        CheckConstraint("status IN ('draft','prepared')", name='ck_work_plan_status'),
        CheckConstraint("participant_grade BETWEEN 1 AND 11 AND curriculum_grade BETWEEN 1 AND 11",
                        name='ck_work_plan_grades'),
        CheckConstraint(
            "(work_type = 'baseline' AND participant_grade > 1 AND curriculum_grade = participant_grade-1 AND quarter IS NULL) OR (work_type IN ('sor','soch') AND curriculum_grade = participant_grade AND quarter IS NOT NULL AND quarter BETWEEN 1 AND 4 AND subject_id = curriculum_subject_id)",
            name='ck_work_plan_curriculum'),
        CheckConstraint("variant_count BETWEEN 2 AND 10", name='ck_work_plan_variants'),
        CheckConstraint("language_policy IN ('auto','kk','ru','both')", name='ck_work_plan_language'),
        CheckConstraint("education_track IN ('general','emn','ogn') OR education_track IS NULL",
                        name='ck_work_plan_track'),
        CheckConstraint(
            "(curriculum_grade IN (10,11) AND education_track IS NOT NULL) OR (curriculum_grade < 10 AND education_track IS NULL)",
            name='ck_work_plan_track_grade'),
        CheckConstraint(
            "(scope_kind='school' AND school_id IS NOT NULL AND district_id IS NULL AND region_id IS NULL) OR (scope_kind='district' AND district_id IS NOT NULL AND school_id IS NULL AND region_id IS NULL) OR (scope_kind='region' AND region_id IS NOT NULL AND school_id IS NULL AND district_id IS NULL)",
            name='ck_work_plan_scope'),
        Index('ix_work_plan_owner_id', 'created_by_user_id', 'id'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    scope_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    school_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('schools.id', ondelete='RESTRICT'))
    district_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('districts.id', ondelete='RESTRICT'))
    region_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('regions.id', ondelete='RESTRICT'))
    academic_year_start: Mapped[int | None] = mapped_column(Integer)
    section_number: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    title_kk: Mapped[str | None] = mapped_column(String(255))
    title_ru: Mapped[str | None] = mapped_column(String(255))
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey('subjects.id', ondelete='RESTRICT'), nullable=False)
    curriculum_subject_id: Mapped[int] = mapped_column(Integer, ForeignKey('subjects.id', ondelete='RESTRICT'),
                                                       nullable=False)
    participant_grade: Mapped[int] = mapped_column(Integer, nullable=False)
    curriculum_grade: Mapped[int] = mapped_column(Integer, nullable=False)
    work_type: Mapped[str] = mapped_column(String(12), nullable=False)
    input_mode: Mapped[str] = mapped_column(String(12), nullable=False)
    quarter: Mapped[int | None] = mapped_column(Integer)
    education_track: Mapped[str | None] = mapped_column(String(12))
    variant_count: Mapped[int] = mapped_column(Integer, nullable=False)
    language_policy: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default='draft', server_default='draft')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now(), nullable=False)


class AssessmentWorkPlanItem(Base):
    __tablename__ = 'assessment_work_plan_items'
    __table_args__ = (
        UniqueConstraint('work_plan_id', 'variant_no', 'order_no', name='uq_work_plan_item_order'),
        UniqueConstraint('work_plan_id', 'variant_no', 'bank_item_id', name='uq_work_plan_variant_source'),
        CheckConstraint('variant_no BETWEEN 1 AND 10 AND order_no > 0 AND max_score > 0',
                        name='ck_work_plan_item_values'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_plan_id: Mapped[int] = mapped_column(Integer, ForeignKey('assessment_work_plans.id', ondelete='CASCADE'),
                                              nullable=False)
    bank_item_id: Mapped[int] = mapped_column(Integer, ForeignKey('question_bank_items.id', ondelete='RESTRICT'),
                                              nullable=False)
    variant_no: Mapped[int] = mapped_column(Integer, nullable=False)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    question_type: Mapped[str] = mapped_column(String(32), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    max_score: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    objectives: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    payloads: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
