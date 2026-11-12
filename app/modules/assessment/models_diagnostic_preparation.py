"""Persistent preparation cursor; credentials are derived, never stored in plaintext."""
from datetime import datetime
from sqlalchemy import Integer,String,ForeignKey,CheckConstraint,UniqueConstraint,DateTime,func,Index
from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.db.base import Base


class DiagnosticPreparation(Base):
    __tablename__='diagnostic_preparations'
    __table_args__=(UniqueConstraint('owner_id','request_key',name='uq_diagnostic_preparation_request'),
        CheckConstraint("state IN ('queued','running','failed','completed','cancelled')",name='ck_diagnostic_preparation_state'),
        CheckConstraint('cursor >= 0 AND pupil_count BETWEEN 0 AND 100000',name='ck_diagnostic_preparation_counts'),
        Index('ix_diagnostic_preparation_queue','state','id'))
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    session_id:Mapped[int]=mapped_column(ForeignKey('diagnostic_sessions.id',ondelete='RESTRICT'),unique=True,nullable=False)
    owner_id:Mapped[int]=mapped_column(ForeignKey('users.id',ondelete='RESTRICT'),nullable=False)
    request_key:Mapped[str]=mapped_column(String(32),nullable=False)
    state:Mapped[str]=mapped_column(String(12),default='queued',nullable=False)
    spec:Mapped[dict]=mapped_column(JSONB,nullable=False)
    nonce:Mapped[str]=mapped_column(String(32),nullable=False)
    key_tag:Mapped[str]=mapped_column(String(64),nullable=False)
    cursor:Mapped[int]=mapped_column(Integer,default=0,nullable=False)
    pupil_count:Mapped[int]=mapped_column(Integer,default=0,nullable=False)
    error:Mapped[str | None]=mapped_column(String(1000))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
