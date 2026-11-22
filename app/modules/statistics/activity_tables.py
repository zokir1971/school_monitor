"""Compact school/day/module facts; no user identifiers or request payloads."""
from sqlalchemy import Table, Column, Integer, String, Date, DateTime, ForeignKey, CheckConstraint, Index
from app.db.base import Base

activity_days = Table(
    'school_activity_days', Base.metadata,
    Column('school_id', Integer, ForeignKey('schools.id', ondelete='CASCADE'), primary_key=True),
    Column('day', Date, primary_key=True),
    Column('module', String(24), primary_key=True),
    Column('first_at', DateTime(timezone=True), nullable=False),
    Column('last_at', DateTime(timezone=True), nullable=False),
    CheckConstraint("module IN ('login','planning','tasks','reports','reviews','staff','education','assessment')", name='ck_school_activity_module'),
    Index('ix_school_activity_period', 'day', 'school_id'),
)
activity_state = Table(
    'school_activity_state', Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('started_at', DateTime(timezone=True), nullable=False),
    CheckConstraint('id = 1', name='ck_school_activity_singleton'),
)
