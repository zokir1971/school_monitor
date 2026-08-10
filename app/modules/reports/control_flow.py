from app.modules.planning.enums import (
    ControlScope,
    ControlForm,
    ControlKind,
)
from app.modules.reports.enums import ReportType


PRIMARY_CLASS_GROUP = "1_4"
MIDDLE_CLASS_GROUP = "5_9"
HIGH_CLASS_GROUP = "10_11"

PRIMARY_PARALLELS = {"1", "2", "3", "4"}
SUBJECT_PARALLELS = {"5", "6", "7", "8", "9", "10", "11"}


CLASS_PRIMARY_REPORTS = [
    ReportType.LESSON_OBSERVATION,
    ReportType.KNOWLEDGE_QUALITY_TABLE,
    ReportType.READING_SPEED_TABLE,
    ReportType.CHECKING_NOTEBOOKS_TABLE,
    ReportType.CLASS_SUMMARY,
    ReportType.ANALYTICAL_REFERENCE,
]

CLASS_SUBJECT_REPORTS = [
    ReportType.LESSON_OBSERVATION,
    ReportType.KNOWLEDGE_QUALITY_TABLE,
    ReportType.CHECKING_NOTEBOOKS_TABLE,
    ReportType.CLASS_SUMMARY,
    ReportType.ANALYTICAL_REFERENCE,
]

SUBJECT_REPORTS = [
    ReportType.LESSON_OBSERVATION,
    ReportType.KNOWLEDGE_QUALITY_TABLE,
    ReportType.CHECKING_NOTEBOOKS_TABLE,
    ReportType.ANALYTICAL_REFERENCE,
]

TEACHER_REPORTS = [
    ReportType.LESSON_OBSERVATION,
    ReportType.KNOWLEDGE_QUALITY_TABLE,
    ReportType.CHECKING_NOTEBOOKS_TABLE,
    ReportType.ANALYTICAL_REFERENCE,
]

DOCUMENT_REPORTS = [
    ReportType.DOCUMENT_ANALYSIS,
    ReportType.ANALYTICAL_REFERENCE,
]

COMPLEX_REPORTS = [
    ReportType.LESSON_OBSERVATION,
    ReportType.KNOWLEDGE_QUALITY_TABLE,
    ReportType.CHECKING_NOTEBOOKS_TABLE,
    ReportType.READING_SPEED_TABLE,
    ReportType.DOCUMENT_ANALYSIS,
    ReportType.ANALYTICAL_REFERENCE,
    ReportType.CLASS_SUMMARY,
    ReportType.TEACHER_ANALYSIS,
]


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
}


LOGIC_RULES = {
    ControlScope.CLASS: {
        "forms": [
            ControlForm.CLASS_GENERALIZING,
            ControlForm.THEMATIC_GENERALIZING,
            ControlForm.OVERVIEW,
        ],
    },
    ControlScope.PARALLEL: {
        "forms": [
            ControlForm.CLASS_GENERALIZING,
            ControlForm.THEMATIC_GENERALIZING,
            ControlForm.COMPLEX_GENERALIZING,
            ControlForm.OVERVIEW,
        ],
    },
    ControlScope.SUBJECT: {
        "forms": [
            ControlForm.SUBJECT_GENERALIZING,
            ControlForm.THEMATIC_GENERALIZING,
            ControlForm.OVERVIEW,
        ],
    },
    ControlScope.TEACHER: {
        "forms": [
            ControlForm.PERSONAL,
            ControlForm.THEMATIC_GENERALIZING,
            ControlForm.OVERVIEW,
        ],
    },
    ControlScope.DOCUMENTATION: {
        "forms": [
            ControlForm.OVERVIEW,
            ControlForm.THEMATIC_GENERALIZING,
        ],
    },
    ControlScope.COMPLEX: {
        "forms": [
            ControlForm.COMPLEX_GENERALIZING,
            ControlForm.OVERVIEW,
        ],
    },
}


REPORT_TARGET_RULES = {
    ReportType.LESSON_OBSERVATION.value: {
        "allowed_target_kinds": [
            "teacher",
            "teacher_subject",
            "teacher_subject_class",
            "primary_teacher",
        ],
        "error": "Лист наблюдения урока доступен только для конкретного учителя.",
    },

    ReportType.CHECKING_NOTEBOOKS_TABLE.value: {
        "allowed_target_kinds": [
            "teacher",
            "teacher_subject",
            "teacher_subject_class",
            "primary_teacher",
        ],
        "error": "Проверка тетрадей доступна только для конкретного учителя.",
    },

    ReportType.KNOWLEDGE_QUALITY_TABLE.value: {
        "allowed_target_kinds": [
            "teacher",
            "teacher_subject",
            "teacher_subject_class",
            "primary_teacher",
            "class_subject",
            "subject",
            "class",
            "parallel",
        ],
        "error": "Для таблицы качества знаний нужна корректная цель контроля.",
    },

    ReportType.READING_SPEED_TABLE.value: {
        "allowed_target_kinds": [
            "class",
            "parallel",
            "primary_teacher",
            "teacher_subject_class",
        ],
        "error": "Скорость чтения доступна только для начальных классов.",
    },

    ReportType.DOCUMENT_ANALYSIS.value: {
        "allowed_target_kinds": [
            "documentation",
            "complex",
        ],
        "error": "Анализ документов доступен только для документации.",
    },

    ReportType.ANALYTICAL_REFERENCE.value: {
        "allowed_target_kinds": [
            "teacher",
            "teacher_subject",
            "teacher_subject_class",
            "primary_teacher",
            "class",
            "parallel",
            "subject",
            "class_subject",
            "documentation",
            "complex",
        ],
        "error": "Аналитическая справка недоступна для выбранной цели.",
    },

    ReportType.CLASS_SUMMARY.value: {
        "allowed_target_kinds": [
            "class",
            "parallel",
            "class_subject",
        ],
        "error": "Сводная таблица доступна только для класса или параллели.",
    },

    ReportType.TEACHER_ANALYSIS.value: {
        "allowed_target_kinds": [
            "teacher",
            "teacher_subject",
            "teacher_subject_class",
            "primary_teacher",
        ],
        "error": "Анализ работы учителя доступен только для конкретного учителя.",
    },
}

TARGET_KIND_ALIASES: dict[str, str] = {
    # В сохранённых данных сейчас встречается такое название,
    # а в REPORT_TARGET_RULES используется "parallel".
    "parallel_class": "parallel",
}


def normalize_report_target_kind(
        target_kind: str | None,
) -> str:
    """
    Нормализовать техническое имя цели отчёта.

    Позволяет поддерживать старые или альтернативные
    названия target_kind без дублирования правил.
    """

    normalized = str(
        target_kind or ""
    ).strip()

    return TARGET_KIND_ALIASES.get(
        normalized,
        normalized,
    )


def is_report_target_assignable(
        *,
        report_code: str,
        target_kind: str | None,
) -> bool:
    """
    Проверить, является ли выбранная строка отчёта
    самостоятельным объектом распределения.

    Строка участвует в распределении только тогда,
    когда её target_kind допустим для указанного
    типа отчёта согласно REPORT_TARGET_RULES.
    """

    rule = REPORT_TARGET_RULES.get(
        str(report_code or "").strip()
    )

    # Для отчётов без специальных ограничений
    # сохраняем прежнее поведение.
    if rule is None:
        return True

    normalized_target_kind = (
        normalize_report_target_kind(
            target_kind
        )
    )

    return (
        normalized_target_kind
        in rule["allowed_target_kinds"]
    )


def reports_to_ui(reports: list[ReportType]) -> list[dict]:
    return [
        {
            "code": report.value,
            "label": report.label_kz,
        }
        for report in reports
    ]


def get_available_reports_for_selection(
        *,
        scope: str,
        class_groups: list[str] | None = None,
        parallel_classes: list[str] | None = None,
) -> list[str]:
    class_groups = class_groups or []
    parallel_classes = parallel_classes or []

    try:
        scope_enum = ControlScope(scope)
    except ValueError:
        return []

    if scope_enum == ControlScope.CLASS:
        if PRIMARY_CLASS_GROUP in class_groups:
            return [x.value for x in CLASS_PRIMARY_REPORTS]

        if MIDDLE_CLASS_GROUP in class_groups or HIGH_CLASS_GROUP in class_groups:
            return [x.value for x in CLASS_SUBJECT_REPORTS]

        return [x.value for x in CLASS_SUBJECT_REPORTS]

    if scope_enum == ControlScope.PARALLEL:
        if any(x in PRIMARY_PARALLELS for x in parallel_classes):
            return [x.value for x in CLASS_PRIMARY_REPORTS]

        if any(x in SUBJECT_PARALLELS for x in parallel_classes):
            return [x.value for x in CLASS_SUBJECT_REPORTS]

        return [x.value for x in CLASS_SUBJECT_REPORTS]

    if scope_enum == ControlScope.SUBJECT:
        return [x.value for x in SUBJECT_REPORTS]

    if scope_enum == ControlScope.TEACHER:
        return [x.value for x in TEACHER_REPORTS]

    if scope_enum == ControlScope.DOCUMENTATION:
        return [x.value for x in DOCUMENT_REPORTS]

    if scope_enum == ControlScope.COMPLEX:
        return [x.value for x in COMPLEX_REPORTS]

    return []


def build_control_flow_for_ui(
        *,
        subjects: list[dict] | None = None,
        all_teachers: list[dict] | None = None,
        teachers_by_subject: dict[str, list[dict]] | None = None,
        primary_teachers: list[dict] | None = None,
):
    subjects = subjects or []
    all_teachers = all_teachers or []
    teachers_by_subject = teachers_by_subject or {}
    primary_teachers = primary_teachers or []

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
            ControlScope.CLASS.value: {
                "1_4": reports_to_ui(CLASS_PRIMARY_REPORTS),
                "5_9": reports_to_ui(CLASS_SUBJECT_REPORTS),
                "10_11": reports_to_ui(CLASS_SUBJECT_REPORTS),
                "default": reports_to_ui(CLASS_SUBJECT_REPORTS),
            },
            ControlScope.PARALLEL.value: {
                "primary": reports_to_ui(CLASS_PRIMARY_REPORTS),
                "subject": reports_to_ui(CLASS_SUBJECT_REPORTS),
                "default": reports_to_ui(CLASS_SUBJECT_REPORTS),
            },
            ControlScope.SUBJECT.value: reports_to_ui(SUBJECT_REPORTS),
            ControlScope.TEACHER.value: reports_to_ui(TEACHER_REPORTS),
            ControlScope.DOCUMENTATION.value: reports_to_ui(DOCUMENT_REPORTS),
            ControlScope.COMPLEX.value: reports_to_ui(COMPLEX_REPORTS),
        },
        "details_by_scope": {
            ControlScope.CLASS.value: {
                "type": "checkbox",
                "name": "class_groups",
                "label": "Сыныптар тобы",
                "options": [
                    {"code": "1_4", "label": "1-4 сынып"},
                    {"code": "5_9", "label": "5-9 сынып"},
                    {"code": "10_11", "label": "10-11 сынып"},
                ],
            },
            ControlScope.PARALLEL.value: {
                "type": "checkbox",
                "name": "parallel_classes",
                "label": "Параллельдер",
                "options": [
                    {"code": str(i), "label": f"{i}-сынып"}
                    for i in range(1, 12)
                ],
            },
            ControlScope.SUBJECT.value: {
                "type": "checkbox",
                "name": "subjects",
                "label": "Пәндер",
                "options": subjects,
            },
            ControlScope.TEACHER.value: {
                "type": "checkbox",
                "name": "subjects",
                "label": "Пәндер",
                "options": subjects,
            },
            ControlScope.DOCUMENTATION.value: {
                "type": "info",
                "name": "documentation",
                "label": "Құжаттар",
                "options": [],
            },
            ControlScope.COMPLEX.value: {
                "type": "checkbox",
                "name": "subjects",
                "label": "Пәндер",
                "options": subjects,
            },
        },
        "teachers": all_teachers,
        "teachers_by_subject": teachers_by_subject,
        "primary_teachers": primary_teachers,
    }


def validate_control_selection(
        scope: str,
        kind: str,
        form: str,
        report: str,
        *,
        class_groups: list[str] | None = None,
        parallel_classes: list[str] | None = None,
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

    valid_reports = set(
        get_available_reports_for_selection(
            scope=scope,
            class_groups=class_groups,
            parallel_classes=parallel_classes,
        )
    )

    if form not in valid_forms:
        return False, "Эта форма контроля недоступна для выбранного объекта"

    if report not in valid_reports:
        return False, "Этот тип отчета недоступен для выбранного объекта"

    return True, None


def validate_report_target(
        *,
        report_code: str,
        target_kind: str | None,
) -> tuple[bool, str | None]:
    """
    Проверить допустимость цели для выбранного типа отчёта.
    """

    rule = REPORT_TARGET_RULES.get(
        str(report_code or "").strip()
    )

    if not rule:
        return True, None

    normalized_target_kind = (
        normalize_report_target_kind(
            target_kind
        )
    )

    if (
        normalized_target_kind
        in rule["allowed_target_kinds"]
    ):
        return True, None

    return False, rule["error"]
