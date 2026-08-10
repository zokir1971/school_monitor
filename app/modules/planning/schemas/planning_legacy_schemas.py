from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.planning.enums import PlanItemStatus, PlanPeriodType
from app.modules.reports.enums import DocumentStatus, DocumentType


class PlanDirectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    short_title: str
    full_title: str | None = None
    is_active: bool
    created_by_user_id: int | None = None
    created_at: datetime


class PlanDirectionCreate(BaseModel):
    short_title: str = Field(min_length=3, max_length=120)
    full_title: str | None = Field(default=None, max_length=800)
    is_active: bool = True


class PlanDirectionUpdate(BaseModel):
    short_title: str | None = Field(default=None, min_length=3, max_length=200)
    full_title: str | None = Field(default=None, max_length=800)
    is_active: bool | None = None


class PlanTemplateItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int
    direction_id: int
    section_id: int
    title: str
    description: str | None = None
    risk_text: str | None = None
    decision_text: str | None = None
    created_at: datetime


class PlanTemplateItemCreate(BaseModel):
    section_id: int
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    risk_text: str | None = None
    decision_text: str | None = None


class SchoolPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int
    school_id: int
    academic_year: str | None
    status: str
    created_at: datetime


class SchoolPlanItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    school_plan_id: int
    direction_id: int
    title: str
    description: str | None = None
    period_type: PlanPeriodType
    period_value: str | None = None
    status: PlanItemStatus
    comment: str | None = None
    completed_at: datetime | None = None


class SchoolPlanCreate(BaseModel):
    academic_year: str = Field(min_length=4, max_length=20)  # "2026-2027"
    template_id: int | None = None


class SchoolPlanItemUpdate(BaseModel):
    status: PlanItemStatus | None = None
    comment: str | None = Field(default=None, max_length=5000)


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    school_id: int
    plan_id: int | None = None
    doc_type: DocumentType
    title: str
    file_path: str
    status: DocumentStatus
    archived_at: datetime | None = None
    created_by_user_id: int | None = None
    created_at: datetime


class DocumentCreate(BaseModel):
    school_id: int
    plan_id: int | None = None
    doc_type: DocumentType
    title: str = Field(min_length=3, max_length=500)
    file_path: str = Field(min_length=3, max_length=1000)


class ArchiveDocumentIn(BaseModel):
    archived: bool = True


class PlanTemplateCreate(BaseModel):
    name: str = Field(min_length=3, max_length=300)
    academic_year: str | None = Field(default=None, max_length=20)


class PlanTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    academic_year: str | None
    is_active: bool
    created_by_user_id: int | None
    created_at: datetime
