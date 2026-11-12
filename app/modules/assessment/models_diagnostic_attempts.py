"""One immutable presentation and response stream per pupil and subject."""
from datetime import datetime
from sqlalchemy import Integer, String, ForeignKey, DateTime, CheckConstraint, UniqueConstraint, Index, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.db.base import Base


class DiagnosticAttempt(Base):
    __tablename__ = 'diagnostic_attempts'
    __table_args__ = (
        UniqueConstraint('assessment_student_id', name='uq_diagnostic_attempt_student'),
        Index('ix_diagnostic_result_queue', 'id', postgresql_where=text("status IN ('submitted','expired') AND assessment_student_id IS NULL AND grading_error IS NULL")),
        UniqueConstraint('participant_id', 'diagnostic_subject_id', name='uq_diagnostic_attempt'),
        CheckConstraint("status IN ('active','submitted','expired')", name='ck_diagnostic_attempt_status'),
        CheckConstraint('version >= 0 AND deadline_at > started_at', name='ck_diagnostic_attempt_time'),
        Index('ix_diagnostic_attempt_deadline', 'status', 'deadline_at'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_id: Mapped[int] = mapped_column(Integer, ForeignKey('diagnostic_participants.id', ondelete='RESTRICT'), nullable=False, index=True)
    diagnostic_subject_id: Mapped[int] = mapped_column(Integer, ForeignKey('diagnostic_subjects.id', ondelete='RESTRICT'), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    presentation: Mapped[list] = mapped_column(JSONB, nullable=False)
    private_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    responses: Mapped[dict] = mapped_column(JSONB, nullable=False)

    navigation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    assessment_student_id: Mapped[int | None] = mapped_column(ForeignKey('assessment_students.id', name='fk_diagnostic_attempt_student', ondelete='RESTRICT'), nullable=True)
    grading_error: Mapped[str | None] = mapped_column(String(32), nullable=True)
