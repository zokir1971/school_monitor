"""Assignments freeze the work plan and participant identity/language/variant."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import Integer, String, ForeignKey, UniqueConstraint, CheckConstraint, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class AssessmentWorkAssignment(Base):
    __tablename__ = 'assessment_work_assignments'
    __table_args__ = (CheckConstraint('academic_year_start BETWEEN 2000 AND 2100', name='ck_work_assignment_year'),
                      Index('ix_work_assignment_plan', 'work_plan_id', 'id'))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_plan_id: Mapped[int] = mapped_column(ForeignKey('assessment_work_plans.id', ondelete='RESTRICT'),
                                              nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    academic_year_start: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AssessmentWorkParticipant(Base):
    __tablename__ = 'assessment_work_participants'
    __table_args__ = (
        UniqueConstraint('work_plan_id', 'student_id', name='uq_work_plan_student'),
        CheckConstraint("language IN ('kk','ru') AND variant_no BETWEEN 1 AND 10", name='ck_work_participant_values'),
        Index('ix_work_participant_assignment', 'assignment_id', 'id'),
        Index('ix_work_participant_plan_id', 'work_plan_id', 'id'),
        Index('ix_work_participant_class_variant', 'work_plan_id', 'school_class_id', 'variant_no'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey('assessment_work_assignments.id', ondelete='RESTRICT'),
                                               nullable=False)
    work_plan_id: Mapped[int] = mapped_column(ForeignKey('assessment_work_plans.id', ondelete='RESTRICT'),
                                              nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey('school_students.id', ondelete='RESTRICT'), nullable=False)
    school_id: Mapped[int] = mapped_column(ForeignKey('schools.id', ondelete='RESTRICT'), nullable=False)
    school_class_id: Mapped[int] = mapped_column(ForeignKey('school_classes.id', ondelete='RESTRICT'), nullable=False)
    full_name: Mapped[str] = mapped_column(String(455), nullable=False)
    school_name: Mapped[str] = mapped_column(String(255), nullable=False)
    class_label: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    variant_no: Mapped[int] = mapped_column(Integer, nullable=False)
