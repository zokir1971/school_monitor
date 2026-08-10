# app/db/types.py
# Типы одинаковые Python Enum ↔ SQLAlchemy ↔ PostgreSQL ENUM

from __future__ import annotations

from sqlalchemy import Enum as SAEnum

from app.modules.users.enums import UserRole

from app.modules.planning.enums import (
    AssignmentKind,
    MonthPlanNotificationStatus,
    PlanItemStatus,
    PlanPeriodType,
    PlanStatus,
    ResponsibleRole,
    ReviewPlace,
)

from app.modules.reports.enums import (
    DocumentStatus,
    DocumentType,
    ReportAssignmentStatus,
    TaskDocumentSource,
    TaskDocumentStatus,
)


# =========================================================
# ENUM HELPERS
# =========================================================

def enum_values(enum_cls):
    """
    Возвращает значения Python Enum,
    которые сохраняются в PostgreSQL ENUM.
    """
    return [
        item.value
        for item in enum_cls
    ]


def enum_labels(enum_cls):
    """
    Возвращает словарь:

        value -> label_kz
    """
    return {
        item.value: getattr(
            item,
            "label_kz",
            item.value,
        )
        for item in enum_cls
    }


def enum_items(
    enum_cls,
    selected_values: list[str] | None = None,
):
    """
    Возвращает элементы enum для интерфейса.
    """
    selected = set(
        selected_values or []
    )

    return [
        {
            "value": item.value,
            "label_kz": getattr(
                item,
                "label_kz",
                item.value,
            ),
        }
        for item in enum_cls
        if (
            not selected
            or item.value in selected
        )
    ]


# =========================================================
# USERS
# =========================================================

USER_ROLE_ENUM = SAEnum(
    UserRole,
    name="user_role",
    values_callable=enum_values,
    native_enum=True,
    validate_strings=True,
)


# =========================================================
# PLANNING
# =========================================================

RESPONSIBLE_ROLE_ENUM = SAEnum(
    ResponsibleRole,
    name="responsible_role_enum",
    values_callable=enum_values,
    native_enum=True,
    validate_strings=True,
)


ASSIGNMENT_KIND_ENUM = SAEnum(
    AssignmentKind,
    name="assignment_kind_enum",
    values_callable=enum_values,
    native_enum=True,
    validate_strings=True,
)


MONTH_PLAN_NOTIFICATION_STATUS_ENUM = SAEnum(
    MonthPlanNotificationStatus,
    name="month_plan_notification_status_enum",
    values_callable=enum_values,
    native_enum=True,
    validate_strings=True,
)


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


REVIEW_PLACE_ENUM = SAEnum(
    ReviewPlace,
    name="review_place",
    values_callable=enum_values,
    native_enum=True,
    validate_strings=True,
)


# =========================================================
# DOCUMENTS / REPORTS
# =========================================================

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


REPORT_ASSIGNMENT_STATUS_ENUM = SAEnum(
    ReportAssignmentStatus,
    name="report_assignment_status_enum",
    values_callable=enum_values,
    native_enum=True,
    validate_strings=True,
    create_type=False,
)
