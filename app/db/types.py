# app/db/types.py (Типы одинаковые Python Enum ↔ SQLAlchemy ↔ Postgres ENUM)

from __future__ import annotations

from sqlalchemy import Enum as SAEnum
from app.modules.users.enums import UserRole
from app.modules.planning.enums import (
    PlanPeriodType,
    PlanStatus,
    PlanItemStatus,
    ResponsibleRole,
    ReviewPlace,
    AssignmentKind
)
from app.modules.reports.enums import DocumentType, DocumentStatus, TaskDocumentStatus, TaskDocumentSource


def enum_values(enum_cls):
    return [e.value for e in enum_cls]


def enum_labels(enum_cls):
    return {e.value: getattr(e, "label_kz", e.value) for e in enum_cls}


def enum_items(enum_cls, selected_values: list[str] | None = None):
    selected = set(selected_values or [])
    return [
        {
            "value": e.value,
            "label_kz": getattr(e, "label_kz", e.value),
        }
        for e in enum_cls
        if not selected or e.value in selected
    ]


USER_ROLE_ENUM = SAEnum(
    UserRole,
    name="user_role",  # один тип в Postgres
    values_callable=enum_values,  # используем .value (lowercase)
    native_enum=True,
    validate_strings=True,
)

RESPONSIBLE_ROLE_ENUM = SAEnum(
    ResponsibleRole,
    name="responsible_role_enum",
    values_callable=enum_values,
    native_enum=True,  # для Postgres (создаёт TYPE)
    validate_strings=True,  # защита от неправильных строк
)

ASSIGNMENT_KIND_ENUM = SAEnum(
    AssignmentKind,
    name="assignment_kind_enum",
    values_callable=enum_values,
    native_enum=True,
    validate_strings=True,
)

# =========================================================
# SQLAlchemy Enum objects (ОДИН ОБЪЕКТ НА ВЕСЬ ПРОЕКТ)
# =========================================================

PLAN_PERIOD_ENUM = SAEnum(
    PlanPeriodType,
    name="plan_period_type",
    values_callable=enum_values,
    native_enum=True,
    validate_strings=True,
)

PLAN_STATUS_ENUM = SAEnum(
    PlanStatus,
    name="plan_status",
    values_callable=enum_values,
    native_enum=True,
    validate_strings=True,
)

PLAN_ITEM_STATUS_ENUM = SAEnum(
    PlanItemStatus,
    name="plan_item_status",
    values_callable=enum_values,
    native_enum=True,
    validate_strings=True,
)

DOCUMENT_TYPE_ENUM = SAEnum(
    DocumentType,
    name="document_type",
    values_callable=enum_values,
    native_enum=True,
    validate_strings=True,
)

DOCUMENT_STATUS_ENUM = SAEnum(
    DocumentStatus,
    name="document_status",
    values_callable=enum_values,
    native_enum=True,
    validate_strings=True,
)

REVIEW_PLACE_ENUM = SAEnum(
    ReviewPlace,
    name="review_place",
    values_callable=enum_values,
    native_enum=True,
    validate_strings=True,
)


TASK_DOCUMENT_STATUS_ENUM = SAEnum(
    TaskDocumentStatus,
    name="task_document_status_enum",
    values_callable=enum_values,
    native_enum=True,
    validate_strings=True,
    create_type=False,
)

TASK_DOCUMENT_SOURCE_ENUM = SAEnum(
    TaskDocumentSource,
    name="task_document_source_enum",
    values_callable=enum_values,
    native_enum=True,
    validate_strings=True,
    create_type=False,
)
