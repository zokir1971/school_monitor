from app.core.feature_flags import report_enabled
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
    ReportType.CLASS_SUMMARY,
]

TEACHER_REPORTS = [
    ReportType.TEACHER_ANALYSIS,
    ReportType.LESSON_OBSERVATION,
    ReportType.KNOWLEDGE_QUALITY_TABLE,
    ReportType.CHECKING_NOTEBOOKS_TABLE,
    ReportType.ANALYTICAL_REFERENCE,
    ReportType.CLASS_SUMMARY,
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
            "report_area",
            "teacher",
            "teacher_subject",
            "teacher_subject_class",
            "primary_teacher",
            "class_subject",
            "subject",
            "class",
            "class_group",
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
            "report_area",
            "class",
            "class_group",
            "teacher",
            "primary_teacher",
            "subject",
            "parallel",
            "class_subject",
        ],
        "error": "Для обобщённого анализа выберите учителя, предмет или класс. / Жалпылама талдау үшін мұғалімді, "
                 "пәнді немесе сыныпты таңдаңыз.",
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

    if not report_enabled(report_code):return False
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
        for report in reports if report_enabled(report.value)
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
            return [x.value for x in CLASS_PRIMARY_REPORTS if report_enabled(x.value)]

        if MIDDLE_CLASS_GROUP in class_groups or HIGH_CLASS_GROUP in class_groups:
            return [x.value for x in CLASS_SUBJECT_REPORTS if report_enabled(x.value)]

        return [x.value for x in CLASS_SUBJECT_REPORTS if report_enabled(x.value)]

    if scope_enum == ControlScope.PARALLEL:
        if any(x in PRIMARY_PARALLELS for x in parallel_classes):
            return [x.value for x in CLASS_PRIMARY_REPORTS if report_enabled(x.value)]

        if any(x in SUBJECT_PARALLELS for x in parallel_classes):
            return [x.value for x in CLASS_SUBJECT_REPORTS if report_enabled(x.value)]

        return [x.value for x in CLASS_SUBJECT_REPORTS if report_enabled(x.value)]

    if scope_enum == ControlScope.SUBJECT:
        return [x.value for x in SUBJECT_REPORTS if report_enabled(x.value)]

    if scope_enum == ControlScope.TEACHER:
        return [x.value for x in TEACHER_REPORTS if report_enabled(x.value)]

    if scope_enum == ControlScope.DOCUMENTATION:
        return [x.value for x in DOCUMENT_REPORTS if report_enabled(x.value)]

    if scope_enum == ControlScope.COMPLEX:
        return [x.value for x in COMPLEX_REPORTS if report_enabled(x.value)]

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


def catalog_subject_classes(catalog):
    """Real school/year pairs. Teaching is a legacy fallback, never a Cartesian product."""
    source = catalog.get('subject_classes', catalog.get('teaching', []))
    return {(int(row['subject_id']),int(row['class_id'])) for row in source}


def report_algorithm_bounds(parameters, target_kind, target_value, catalog):
    """Narrow each report using stored pairs and live school/year relations; no DB writes."""
    result = dict(parameters or {})
    if result.get('version') != 2:
        return result
    classes = set(result.get('class_ids', []))
    subjects = set(result.get('subject_ids', []))
    restrict_subjects = result.get('scope') != 'class' or target_kind in ('subject','teacher','primary_teacher')
    pairs = {(sid,cid) for sid,cid in catalog_subject_classes(catalog) if cid in classes and (not restrict_subjects or not subjects or sid in subjects)}
    if 'subject_class_pairs' in result:
        stored = {(row['subject_id'],row['class_id']) for row in result['subject_class_pairs']}
        pairs &= stored
    raw = str(target_value)
    if target_kind == 'report_area':
        area = next((a for a in result.get('report_areas',[]) if a['id'] == raw), None)
        area_pairs = {(p['subject_id'],p['class_id']) for p in area['pairs']} if area else set()
        pairs &= area_pairs
        result['scope'] = 'report_area'
        restrict_subjects = True
    if target_kind == 'subject':
        matches = {s['id'] for s in catalog['subjects'] if raw in (str(s['id']),s.get('name_ru'),s.get('name_kz'))}
        pairs = {(sid,cid) for sid,cid in pairs if sid in matches}
    elif target_kind in ('teacher','primary_teacher'):
        teaching = {(row['subject_id'],row['class_id']) for row in catalog['teaching'] if str(row['teacher_id']) == raw}
        pairs &= teaching
    elif target_kind == 'class':
        matches = {c['id'] for c in catalog['classes'] if raw in (str(c['id']),c['name'])}
        pairs = {(sid,cid) for sid,cid in pairs if cid in matches}
    elif target_kind in ('parallel','parallel_class'):
        matches = {c['id'] for c in catalog['classes'] if str(c['grade_level']) == raw}
        pairs = {(sid,cid) for sid,cid in pairs if cid in matches}
    result.update(class_ids=sorted({cid for sid,cid in pairs}),
        subject_class_pairs=[dict(subject_id=sid,class_id=cid) for sid,cid in sorted(pairs)])
    if restrict_subjects:
        result['subject_ids'] = sorted({sid for sid,cid in pairs})
    return result


def algorithm_context_label(parameters, target_kind, target_value, catalog, language='ru'):
    if (parameters or {}).get('version') != 2 or target_kind == 'documentation':
        return (parameters or {}).get('context_label','')
    bounds = report_algorithm_bounds(parameters,target_kind,target_value,catalog)
    classes = {c['id']:c['name'] for c in catalog['classes']}
    subjects = {s['id']:(s.get('name_kz') or s.get('name_ru') if language=='kk' else s.get('name_ru') or s.get('name_kz')) for s in catalog['subjects']}
    pairs = bounds.get('subject_class_pairs',[])
    if target_kind == 'subject':
        return ', '.join(classes[cid] for cid in bounds.get('class_ids',[]) if cid in classes)
    return '; '.join(str(subjects[sid])+': '+', '.join(classes[p['class_id']] for p in pairs if p['subject_id']==sid and p['class_id'] in classes) for sid in sorted({p['subject_id'] for p in pairs}) if sid in subjects)


def validate_report_areas(raw, allowed_pairs, codes):
    import re
    if raw is None:
        return None
    if not isinstance(raw,dict) or type(raw.get('enabled')) is not bool or not isinstance(raw.get('areas'),list):
        raise ValueError('Проверьте формат областей отчёта. / Есеп ауқымдарының пішімін тексеріңіз.')
    if not raw['enabled']:
        return []
    if raw.get('coverage_version') != 1:
        raise ValueError('Обновите форму алгоритма для проверки охвата предметов и классов. / Пәндер мен сыныптарды қамтуды тексеру үшін алгоритм нысанын жаңартыңыз.')
    supported = {'knowledge_quality_table','class_summary'} & set(codes)
    if not supported or not raw['areas'] or len(raw['areas']) > 50:
        raise ValueError('Выберите табличный отчёт и от 1 до 50 областей. / Кестелік есеп пен 1–50 ауқымды таңдаңыз.')
    result, ids, occupied = [], set(), set()
    for item in raw['areas']:
        if not isinstance(item,dict):raise ValueError('Некорректная область. / Ауқым дұрыс емес.')
        key = item.get('id'); ru = str(item.get('name_ru') or '').strip(); kk = str(item.get('name_kk') or '').strip()
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',key) or key in ids:
            raise ValueError('Области должны иметь уникальные идентификаторы. / Ауқымдардың идентификаторлары бірегей болуы керек.')
        if not (ru or kk) or max(len(ru),len(kk)) > 180:
            raise ValueError('Укажите название области до 180 символов. / Ауқым атауын 180 таңбаға дейін енгізіңіз.')
        ids.add(key)
        selected_codes = item.get('report_codes')
        if not isinstance(selected_codes,list) or not selected_codes or any(not isinstance(c,str) or c not in supported for c in selected_codes):
            raise ValueError('Выберите доступные отчёты каждой области. / Әр ауқымның қолжетімді есептерін таңдаңыз.')
        pairs = item.get('pairs')
        if not isinstance(pairs,list) or not pairs or len(pairs)>5000:
            raise ValueError('Отметьте предметы и классы каждой области. / Әр ауқымның пәндері мен сыныптарын белгілеңіз.')
        chosen=set()
        for pair in pairs:
            if not isinstance(pair,dict) or type(pair.get('subject_id')) is not int or type(pair.get('class_id')) is not int:
                raise ValueError('Некорректная пара предмет–класс. / Пән–сынып жұбы дұрыс емес.')
            value=(pair['subject_id'],pair['class_id'])
            if value not in allowed_pairs:
                raise ValueError('Область содержит предмет или класс вне текущих параметров: '+(ru or kk)+' / Ауқымда ағымдағы параметрлерге кірмейтін пән не сынып бар: '+(kk or ru))
            chosen.add(value)
        for code in set(selected_codes):
            for sid,cid in chosen:
                token=(code,sid,cid)
                if token in occupied:
                    raise ValueError('Пара предмет–класс повторяется в областях одного типа отчёта. / Пән–сынып жұбы бір есеп түрінің ауқымдарында қайталанады.')
                occupied.add(token)
        result.append(dict(id=key,name_ru=ru or kk,name_kk=kk or ru,report_codes=sorted(set(selected_codes)),
            pairs=[dict(subject_id=sid,class_id=cid) for sid,cid in sorted(chosen)]))
    if supported != {code for a in result for code in a['report_codes']}:
        raise ValueError('Задайте область для каждого выбранного табличного отчёта. / Әр таңдалған кестелік есепке ауқым белгілеңіз.')
    if raw.get('coverage_version') == 1:
        uncovered = {(code,sid,cid) for code in supported for sid,cid in allowed_pairs} - occupied
        exclusions = raw.get('coverage_exclusions',[])
        if not isinstance(exclusions,list) or len(exclusions)>10000:
            raise ValueError('Проверьте исключения охвата. / Қамту ерекшеліктерін тексеріңіз.')
        excluded=set()
        for p in exclusions:
            if not isinstance(p,dict) or type(p.get('subject_id')) is not int or type(p.get('class_id')) is not int or p.get('report_code') not in supported:
                raise ValueError('Некорректное исключение охвата. / Қамту ерекшелігі дұрыс емес.')
            value=(p['report_code'],p['subject_id'],p['class_id'])
            if value not in uncovered:
                raise ValueError('Исключения не соответствуют текущим параметрам. / Ерекшеліктер ағымдағы параметрлерге сәйкес келмейді.')
            excluded.add(value)
        if uncovered-excluded:
            raise ValueError('Есть неохваченные предметы и классы. Нажмите «Добавить неохваченные» либо явно исключите их из проверки. / Қамтылмаған пәндер мен сыныптар бар. «Қамтылмағандарды қосу» түймесін басыңыз немесе оларды тексеруден анық алып тастаңыз.')
    return result


def area_scope(parameters):
    # Display names do not change scope; pair/code changes do.
    return sorted((a['id'],tuple(sorted(a['report_codes'])),tuple(sorted((p['subject_id'],p['class_id']) for p in a['pairs']))) for a in (parameters or {}).get('report_areas',[]))


def build_algorithm_plan(catalog: dict, *, scope: str, report_types: list[str], subject_ids: list[str],
                         class_ids: list[str], parallels: list[str], class_groups: list[str],
                         teacher_ids: list[str], report_teacher_ids: dict[str, list[str]],
                         report_type_map: dict[str, int], task_id: int, form: str | None = None, kind: str | None = None, report_areas: dict | None = None) -> dict:
    """Canonical compiler: validated inputs -> parameters and existing selected-report rows.

    Pure calculation. No session, storage or assignment changes here.
    """
    def positive(values, label):
        result = set()
        for value in values or []:
            try:
                number = int(value)
            except (TypeError, ValueError):
                raise ValueError('Некорректный выбор: ' + label)
            if number <= 0:
                raise ValueError('Некорректный выбор: ' + label)
            result.add(number)
        return sorted(result)
    if scope not in {item.value for item in CONTROL_CONFIG['scopes']}:
        raise ValueError('Выберите объект контроля. / Бақылау нысанын таңдаңыз.')
    if form is not None and form not in {item.value for item in LOGIC_RULES[ControlScope(scope)]['forms']}:
        raise ValueError('Выберите доступную форму контроля. / Қолжетімді бақылау нысанын таңдаңыз.')
    if kind is not None and kind not in {item.value for item in CONTROL_CONFIG['kinds']}:
        raise ValueError('Выберите вид контроля. / Бақылау түрін таңдаңыз.')
    if catalog.get('plan_status') == 'archived' or catalog.get('month_status') == 'archived':
        raise ValueError('Архивный план изменять нельзя. / Мұрағат жоспарын өзгертуге болмайды.')
    subjects = {row['id']: row for row in catalog['subjects']}
    classes = {row['id']: row for row in catalog['classes']}
    chosen_subjects = positive(subject_ids, 'предметы')
    explicit_classes = positive(class_ids, 'классы')
    grades = positive(parallels, 'параллели')
    if not set(chosen_subjects).issubset(subjects) or not set(explicit_classes).issubset(classes):
        raise ValueError('Предметы или классы не входят в школу и учебный год плана. / Пәндер немесе сыныптар мектеп пен жоспардың оқу жылына кірмейді.')
    if any(grade > 12 for grade in grades):
        raise ValueError('Некорректная параллель. / Сынып деңгейі дұрыс емес.')
    codes = list(dict.fromkeys(str(code) for code in (report_types or [])))
    from app.core.feature_access import ensure_report
    for code in codes:ensure_report(code)
    if not codes or any(code not in report_type_map for code in codes):
        raise ValueError('Выберите допустимые отчёты. / Қолжетімді есептерді таңдаңыз.')
    available = set(get_available_reports_for_selection(scope=scope, class_groups=class_groups, parallel_classes=[str(value) for value in grades]))
    if any(code not in available for code in codes):
        raise ValueError('Отчёт недоступен для выбранного объекта контроля. / Есеп таңдалған бақылау нысаны үшін қолжетімсіз.')
    teacher_reports = {'lesson_observation', 'checking_notebooks_table'}
    need_teachers = bool(teacher_reports.intersection(codes) or scope == 'teacher' or 'teacher_analysis' in codes)
    if (need_teachers or scope == 'subject') and not chosen_subjects:
        raise ValueError('Сначала выберите предмет проверки. / Алдымен тексерілетін пәнді таңдаңыз.')
    pool = set(classes)
    if scope == 'parallel':
        if not grades:
            raise ValueError('Выберите параллель. / Сынып деңгейін таңдаңыз.')
        pool = {cid for cid in pool if classes[cid]['grade_level'] in grades}
    elif scope == 'class':
        if not explicit_classes:
            raise ValueError('Выберите конкретные классы. / Нақты сыныптарды таңдаңыз.')
        if class_groups:
            allowed_grades = set()
            for group in class_groups:
                if group not in ('1_4', '5_9', '10_11'):
                    raise ValueError('Некорректная группа классов. / Сыныптар тобы дұрыс емес.')
                lo, hi = map(int, group.split('_'))
                allowed_grades.update(range(lo, hi + 1))
            pool = {cid for cid in pool if classes[cid]['grade_level'] in allowed_grades}
    if explicit_classes:
        if not set(explicit_classes).issubset(pool):
            raise ValueError('Классы не соответствуют выбранной области проверки. / Сыныптар таңдалған тексеру ауқымына сәйкес келмейді.')
        pool = set(explicit_classes)
    subject_pairs = catalog_subject_classes(catalog)
    if chosen_subjects and scope in ('subject','teacher','parallel','complex'):
        subject_pool = {cid for sid,cid in subject_pairs if sid in chosen_subjects}
        if explicit_classes and not set(explicit_classes).issubset(subject_pool):
            raise ValueError('В выбранных классах нет выбранных предметов. Уточните классы. / Таңдалған сыныптарда таңдалған пәндер жоқ. Сыныптарды нақтылаңыз.')
        pool &= subject_pool
        if any(not any(s == sid and cid in pool for s,cid in subject_pairs) for sid in chosen_subjects):
            raise ValueError('Для каждого предмета выберите класс, где он предусмотрен учебным планом или действующей нагрузкой. / Әр пән үшін оқу жоспарында не белсенді жүктемеде көрсетілген сыныпты таңдаңыз.')
        if scope == 'parallel' and any(not any(classes[cid]['grade_level'] == grade for cid in pool) for grade in grades):
            raise ValueError('Предмет не предусмотрен в выбранной параллели. / Пән таңдалған сынып деңгейінде қарастырылмаған.')
    if scope not in ('documentation',) and not pool:
        raise ValueError('В выбранной области нет классов учебного года плана. / Таңдалған ауқымда жоспардың оқу жылына сәйкес сыныптар жоқ.')
    loads = [row for row in catalog['teaching'] if row['class_id'] in pool and row['subject_id'] in chosen_subjects]
    teachers = {}
    for row in loads:
        entry = teachers.setdefault(row['teacher_id'], dict(name=row['full_name'], class_ids=set(), subject_ids=set()))
        entry['class_ids'].add(row['class_id']); entry['subject_ids'].add(row['subject_id'])
    selected_teachers = positive(teacher_ids, 'учителя')
    per_report = {code: positive(report_teacher_ids.get(code, []), 'учителя отчёта') for code in teacher_reports if code in codes}
    requested_teachers = set(selected_teachers)
    for values in per_report.values():
        requested_teachers.update(values)
    if not requested_teachers.issubset(teachers):
        raise ValueError('Учитель не ведёт выбранный предмет в выбранных классах и учебном году. / Мұғалім таңдалған пәнді осы сыныптарда және оқу жылында жүргізбейді.')
    if (scope == 'teacher' or 'teacher_analysis' in codes) and not selected_teachers:
        raise ValueError('Отметьте учителей как объект контроля. / Бақылау нысаны ретінде мұғалімдерді белгілеңіз.')
    for code, values in per_report.items():
        if not values:
            title = 'Лист наблюдения урока' if code == 'lesson_observation' else 'Проверка тетрадей'
            raise ValueError(title + ': отметьте проверяемого учителя в общей таблице. / Ортақ кестеде тексерілетін мұғалімді белгілеңіз.')
    def teacher_target(tid):
        return dict(target_kind='teacher', target_value=str(tid), target_label=teachers[tid]['name'])
    def base_targets():
        if scope == 'teacher':
            return [teacher_target(tid) for tid in selected_teachers]
        if scope == 'parallel':
            return [dict(target_kind='parallel_class', target_value=str(grade), target_label=str(grade)) for grade in grades]
        if scope == 'class':
            return [dict(target_kind='class', target_value=str(cid), target_label=classes[cid]['name']) for cid in sorted(pool)]
        if scope in ('subject', 'complex') and chosen_subjects:
            return [dict(target_kind='subject', target_value=str(sid), target_label=subjects[sid]['name_ru'] or subjects[sid]['name_kz']) for sid in chosen_subjects]
        return [dict(target_kind='documentation', target_value=str(task_id), target_label='Документы задачи / Тапсырма құжаттары')]
    area_allowed = {(sid,cid) for sid,cid in subject_pairs if cid in pool and (not chosen_subjects or sid in chosen_subjects)}
    areas = validate_report_areas(report_areas,area_allowed,codes)
    rows = []
    for code in codes:
        # The final reference is prepared at finalization, not assigned as a system worksheet.
        if code == 'analytical_reference':
            continue
        if areas and code in ('knowledge_quality_table','class_summary'):
            targets = [dict(target_kind='report_area',target_value=a['id'],target_label=a['name_ru']) for a in areas if code in a['report_codes']]
        elif code in teacher_reports:
            targets = [teacher_target(tid) for tid in per_report[code]]
        elif code == 'teacher_analysis':
            targets = [teacher_target(tid) for tid in selected_teachers]
        elif code == 'reading_speed_table':
            targets = [dict(target_kind='class', target_value=str(cid), target_label=classes[cid]['name']) for cid in sorted(pool)]
        elif code == 'document_analysis':
            targets = [dict(target_kind='documentation', target_value=str(task_id), target_label='Документы задачи / Тапсырма құжаттары')]
        else:
            targets = base_targets()
        if not targets or any(not is_report_target_assignable(report_code=code, target_kind=row['target_kind']) for row in targets):
            raise ValueError('Отчёт не подходит выбранному объекту: ' + code)
        if code == 'reading_speed_table' and any(classes[cid]['grade_level'] > 4 for cid in pool):
            raise ValueError('Скорость чтения доступна для начальных классов. / Оқу жылдамдығы бастауыш сыныптар үшін қолжетімді.')
        rows.append(dict(report_type_id=report_type_map[code], targets=targets))
    def subject_names(sids):
        return ', '.join(subjects[sid]['name_ru'] or subjects[sid]['name_kz'] for sid in sorted(sids))
    def class_names(cids):
        return ', '.join(classes[cid]['name'] for cid in sorted(cids))
    contexts = {str(tid): dict(class_ids=sorted(entry['class_ids']), subject_ids=sorted(entry['subject_ids']),
                              label=subject_names(entry['subject_ids']) + ' · ' + class_names(entry['class_ids']))
                for tid, entry in teachers.items() if tid in requested_teachers}
    pairs = sorted((sid,cid) for sid,cid in subject_pairs if cid in pool and (scope == 'class' or not chosen_subjects or sid in chosen_subjects))
    subject_contexts = {str(sid):dict(subject_ids=[sid],class_ids=sorted(cid for s,cid in pairs if s==sid),
        label=class_names(cid for s,cid in pairs if s==sid)) for sid in chosen_subjects}
    parameters = dict(version=2, subject_contexts=subject_contexts,
                      subject_class_pairs=[dict(subject_id=sid,class_id=cid) for sid,cid in pairs], scope=scope, year_start=catalog['year_start'], subject_ids=chosen_subjects, class_ids=sorted(pool),
                      selected_class_ids=explicit_classes, parallel_classes=grades, class_groups=list(class_groups or []),
                      teacher_ids=selected_teachers, report_teacher_ids={code: values for code, values in per_report.items()},
                      report_types=codes, teacher_contexts=contexts,
                      context_label=subject_names(chosen_subjects) + (' · ' if chosen_subjects else '') + class_names(pool))
    if areas is not None:
        parameters.update(report_areas_mode=bool(areas),report_areas=areas,report_area_coverage_version=(report_areas or {}).get('coverage_version',0),report_area_exclusions=(report_areas or {}).get('coverage_exclusions',[]) if areas else [])
    for tid, context in contexts.items():
        context['label'] = algorithm_context_label(parameters,'teacher',tid,catalog)
    return dict(parameters=parameters, selected_reports=rows)
