from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MonthItemUpdate(BaseModel):
    """
    Обновление флагов строки месячного плана.
    Используется в bulk-апдейте.
    """
    model_config = ConfigDict(extra="forbid")

    item_id: int
    is_included: bool
    week_of_month: Optional[int] = None
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    notes: Optional[str] = None


class BulkAssignWeekIn(BaseModel):
    week_of_month: int = Field(ge=1, le=6)
    item_ids: list[int] = Field(default_factory=list)


class AssignWeekIn(BaseModel):
    week_of_month: int = Field(ge=1, le=6)
