from app.modules.planning.enums import (
    ControlScope,
    ControlForm,
    ControlKind,
)
from app.modules.reports.enums import ReportType

CONTROL_CONFIG = {
    "scopes": [
        ControlScope.CLASS,
        ControlScope.PARALLEL,
        ControlScope.SUBJECT,
        ControlScope.TEACHER,
        ControlScope.DOCUMENTATION,
        ControlScope.COMPLEX,
    ],
    "kinds": [
        ControlKind.FRONT,
        ControlKind.THEMATIC,
    ],
    "forms": [
        ControlForm.PERSONAL,
        ControlForm.CLASS_GENERALIZING,
        ControlForm.SUBJECT_GENERALIZING,
        ControlForm.THEMATIC_GENERALIZING,
        ControlForm.OVERVIEW,
        ControlForm.COMPLEX_GENERALIZING,
    ],
    "reports": [
        ReportType.LESSON_OBSERVATION,
        ReportType.KNOWLEDGE_QUALITY_TABLE,
        ReportType.CHECKING_NOTEBOOKS_TABLE,
        ReportType.READING_SPEED_TABLE,
        ReportType.DOCUMENT_ANALYSIS,
        ReportType.ANALYTICAL_REFERENCE,
        ReportType.CLASS_SUMMARY,
        ReportType.TEACHER_ANALYSIS,
    ],
}

LOGIC_RULES = {
    ControlScope.TEACHER: {
        "forms": [
            ControlForm.PERSONAL,
            ControlForm.THEMATIC_GENERALIZING,
            ControlForm.OVERVIEW,
        ],
        "reports": [
            ReportType.LESSON_OBSERVATION,
            ReportType.CHECKING_NOTEBOOKS_TABLE,
            ReportType.TEACHER_ANALYSIS,
            ReportType.ANALYTICAL_REFERENCE,
        ],
    },
    ControlScope.CLASS: {
        "forms": [
            ControlForm.CLASS_GENERALIZING,
            ControlForm.THEMATIC_GENERALIZING,
            ControlForm.OVERVIEW,
        ],
        "reports": [
            ReportType.KNOWLEDGE_QUALITY_TABLE,
            ReportType.READING_SPEED_TABLE,
            ReportType.CLASS_SUMMARY,
            ReportType.ANALYTICAL_REFERENCE,
        ],
    },
    ControlScope.PARALLEL: {
        "forms": [
            ControlForm.CLASS_GENERALIZING,
            ControlForm.THEMATIC_GENERALIZING,
            ControlForm.COMPLEX_GENERALIZING,
            ControlForm.OVERVIEW,
        ],
        "reports": [
            ReportType.KNOWLEDGE_QUALITY_TABLE,
            ReportType.READING_SPEED_TABLE,
            ReportType.CLASS_SUMMARY,
            ReportType.ANALYTICAL_REFERENCE,
        ],
    },
    ControlScope.SUBJECT: {
        "forms": [
            ControlForm.SUBJECT_GENERALIZING,
            ControlForm.THEMATIC_GENERALIZING,
            ControlForm.OVERVIEW,
        ],
        "reports": [
            ReportType.LESSON_OBSERVATION,
            ReportType.CHECKING_NOTEBOOKS_TABLE,
            ReportType.KNOWLEDGE_QUALITY_TABLE,
            ReportType.ANALYTICAL_REFERENCE,
        ],
    },
    ControlScope.DOCUMENTATION: {
        "forms": [
            ControlForm.OVERVIEW,
            ControlForm.THEMATIC_GENERALIZING,
        ],
        "reports": [
            ReportType.DOCUMENT_ANALYSIS,
            ReportType.ANALYTICAL_REFERENCE,
        ],
    },
    ControlScope.COMPLEX: {
        "forms": [
            ControlForm.COMPLEX_GENERALIZING,
            ControlForm.OVERVIEW,
        ],
        "reports": [
            ReportType.LESSON_OBSERVATION,
            ReportType.KNOWLEDGE_QUALITY_TABLE,
            ReportType.CHECKING_NOTEBOOKS_TABLE,
            ReportType.READING_SPEED_TABLE,
            ReportType.DOCUMENT_ANALYSIS,
            ReportType.ANALYTICAL_REFERENCE,
            ReportType.CLASS_SUMMARY,
            ReportType.TEACHER_ANALYSIS,
        ],
    },
}


def build_control_flow_for_ui():
    return {
        "scopes": [
            {"code": item.value, "label": item.label_kz}
            for item in CONTROL_CONFIG["scopes"]
        ],
        "kinds": [
            {"code": item.value, "label": item.label_kz}
            for item in CONTROL_CONFIG["kinds"]
        ],
        "forms_by_scope": {
            scope.value: [
                {"code": form.value, "label": form.label_kz}
                for form in data["forms"]
            ]
            for scope, data in LOGIC_RULES.items()
        },
        "reports_by_scope": {
            scope.value: [
                {"code": report.value, "label": report.label_kz}
                for report in data["reports"]
            ]
            for scope, data in LOGIC_RULES.items()
        },
    }


def validate_control_selection(
    scope: str,
    kind: str,
    form: str,
    report: str,
) -> tuple[bool, str | None]:

    valid_scopes = {x.value for x in CONTROL_CONFIG["scopes"]}
    valid_kinds = {x.value for x in CONTROL_CONFIG["kinds"]}

    if scope not in valid_scopes:
        return False, "Недопустимый объект контроля"

    if kind not in valid_kinds:
        return False, "Недопустимый вид контроля"

    try:
        scope_enum = ControlScope(scope)
    except ValueError:
        return False, "Объект контроля не найден"

    rules = LOGIC_RULES.get(scope_enum)
    if not rules:
        return False, "Для выбранного объекта контроля не настроены правила"

    valid_forms = {x.value for x in rules["forms"]}
    valid_reports = {x.value for x in rules["reports"]}

    if form not in valid_forms:
        return False, "Эта форма контроля недоступна для выбранного объекта"

    if report not in valid_reports:
        return False, "Этот тип отчета недоступен для выбранного объекта"

    return True, None
