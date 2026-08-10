from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class CellUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["row4", "row11"]
    row_id: int
    field: str
    value: str | None = None

    school_plan_id: int | None = None
    direction_id: int | None = None


class RowAddIn(BaseModel):
    plan_id: int
    direction_id: int
    kind: str


class RowDeleteIn(BaseModel):
    plan_id: int
    direction_id: int
    kind: str


class Row11MetaUpdateIn(BaseModel):
    period_type: str
    month: Optional[int] = None
    quarter: Optional[int] = None
    period_values: Optional[str] = None
    responsible_role: Optional[str] = None


class Row11PeriodUpdateIn(BaseModel):
    period_type: str
    month: Optional[int] = None
    quarter: Optional[int] = None
    period_values: Optional[str] = None


class Row11ResponsibleUpdateIn(BaseModel):
    responsible_role: Optional[str] = None


class ArchivePlanIn(BaseModel):
    archived: bool = True
