from datetime import datetime
from sqlalchemy import DateTime,ForeignKey,Index,Integer,String,func,text
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base


class AccessRecoveryGrant(Base):
    __tablename__='access_recovery_grants'
    __table_args__=(Index('ix_access_recovery_user_created','user_id','created_at'),
                   Index('uq_access_recovery_open_user','user_id',unique=True,postgresql_where=text('used_at IS NULL AND revoked_at IS NULL')))
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'))
    issued_by_user_id:Mapped[int]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'))
    token_hash:Mapped[str]=mapped_column(String(64),unique=True)
    credential_stamp:Mapped[str]=mapped_column(String(64))
    issuer_stamp:Mapped[str]=mapped_column(String(64))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    used_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    revoked_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))


class AccessRecoveryAudit(Base):
    __tablename__='access_recovery_audit'
    __table_args__=(Index('ix_access_recovery_audit_target','target_user_id','created_at'),)
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    actor_user_id:Mapped[int|None]=mapped_column(ForeignKey('users.id',ondelete='SET NULL'))
    target_user_id:Mapped[int|None]=mapped_column(ForeignKey('users.id',ondelete='SET NULL'))
    action:Mapped[str]=mapped_column(String(24))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())


class AccessRecoveryLimit(Base):
    __tablename__='access_recovery_limits'
    bucket_key:Mapped[str]=mapped_column(String(64),primary_key=True)
    attempts:Mapped[int]=mapped_column(Integer)
    resets_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
