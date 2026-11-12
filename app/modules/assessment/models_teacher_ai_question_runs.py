"""Metadata registration for the durable teacher AI web journal."""
from __future__ import annotations
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TeacherAIQuestionRun(Base):
    __tablename__ = 'teacher_ai_question_runs'
    proposal: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    item_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    __table_args__ = (
        CheckConstraint("status IN ('pending','running','completed','failed')",
                        name='ck_teacher_ai_question_runs_status'),
        Index('ix_teacher_ai_question_runs_user_created', 'user_id', 'created_at'),
    )
    token: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default='pending')
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('question_bank_items.id', ondelete='SET NULL'))
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
