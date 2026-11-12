# app/modules/reports/schemas/execution_dto.py
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass(slots=True)
class ExecutionFormDTO:
    """
    Состояние формы выполнения задачи для UI.
    """

    control_scope: str = ""
    control_form: str = ""
    control_kind: str = ""
    review_result: str = ""

    report_types: list[str] = field(default_factory=list)

    subjects: list[str] = field(default_factory=list)
    class_groups: list[str] = field(default_factory=list)
    parallel_classes: list[str] = field(default_factory=list)

    teacher_id: str = ""
    teacher_ids: list[str] = field(default_factory=list)

    report_teacher_ids: dict[str, list[str]] = field(default_factory=dict)

    school_class_ids: list[str] = field(default_factory=list)
    algorithm_revision: int = 0
    report_areas: list[dict] = field(default_factory=list)
    report_areas_mode: bool = False
    report_area_exclusions: list[dict] = field(default_factory=list)

    generated_reports_json: str = "[]"


    @classmethod
    def from_model(
            cls,
            execution: object | None = None,
        *,
        execution_data: object | None = None,
    ) -> ExecutionFormDTO:
        """
        Построить ExecutionFormDTO из ORM-модели TaskExecutionData.

        Что переносим:
        - control_scope / control_form / control_kind
        - review_result
        - generated_reports_json из relation selected_reports
        - производные списки subjects / class_groups / parallel_classes / teacher_ids
        - teacher_id как строку, если выбран ровно один учитель

        Если execution_data отсутствует:
        - возвращаем пустой DTO
        """
        if execution is not None:
            if execution_data is not None:
                raise TypeError("Pass execution or execution_data, not both")
            execution_data = execution
        if isinstance(execution_data, cls):
            return execution_data
        clean = lambda value: "" if value is None else str(value).strip()
        if not execution_data:
            return cls()

        grouped: dict[tuple[int, str], dict] = {}

        report_types: list[str] = []
        subjects: list[str] = []
        class_groups: list[str] = []
        parallel_classes: list[str] = []
        teacher_ids: list[str] = []
        report_teacher_ids: dict[str, list[str]] = {}

        for item in getattr(execution_data, "selected_reports", []) or []:
            report_type = getattr(item, "report_type", None)
            if not report_type:
                continue

            report_type_id = getattr(report_type, "id", None)
            report_code = getattr(report_type, "code", None)

            if report_type_id is None or not report_code:
                continue

            report_code = str(report_code)
            if report_code not in report_types:
                report_types.append(report_code)

            key = (int(report_type_id), report_code)

            if key not in grouped:
                grouped[key] = {
                    "report_type_id": int(report_type_id),
                    "report_code": str(report_code),
                    "report_label": (
                            getattr(report_type, "name_kz", None)
                            or getattr(report_type, "name_ru", None)
                            or str(report_code)
                    ),
                    "targets": [],
                }

            target_kind = clean(getattr(item, "target_kind", None))
            target_kind = {"subjects": "subject", "class_groups": "class_group", "parallel_classes": "parallel_class", "teacher_id": "teacher", "teacher_ids": "teacher"}.get(target_kind, target_kind)
            target_value = clean(getattr(item, "target_value", None))
            target_label = (
                    clean(getattr(item, "target_label", None))
                    or target_value
            )

            if not target_kind or not target_value:
                continue

            grouped[key]["targets"].append(
                {
                    "kind": target_kind,
                    "value": target_value,
                    "label": target_label,
                }
            )

            if target_kind == "subject":
                if target_value not in subjects:
                    subjects.append(target_value)

            elif target_kind == "class_group":
                if target_value not in class_groups:
                    class_groups.append(target_value)

            elif target_kind == "parallel_class":
                if target_value not in parallel_classes:
                    parallel_classes.append(target_value)

            elif target_kind == "teacher":
                if report_code in ("lesson_observation", "checking_notebooks_table"):
                    values = report_teacher_ids.setdefault(report_code, [])
                    if target_value not in values:
                        values.append(target_value)
                # Per-report subjects must not become global targets on next save.
                if report_code not in ("lesson_observation", "checking_notebooks_table"):
                    if target_value not in teacher_ids:
                        teacher_ids.append(target_value)

        parameters = getattr(execution_data, 'algorithm_parameters', None) or {}
        if parameters.get('version') == 2:
            subjects = [str(value) for value in parameters.get('subject_ids', [])]
            class_groups = list(parameters.get('class_groups', []))
            parallel_classes = [str(value) for value in parameters.get('parallel_classes', [])]
            teacher_ids = [str(value) for value in parameters.get('teacher_ids', [])]
            report_types = list(parameters.get('report_types', report_types))
            report_teacher_ids = {code: [str(value) for value in values] for code, values in parameters.get('report_teacher_ids', {}).items()}
        teacher_id = teacher_ids[0] if len(teacher_ids) == 1 else ""

        return cls(
            control_scope=clean(getattr(execution_data, "control_scope", None)),
            control_form=clean(getattr(execution_data, "control_form", None)),
            control_kind=clean(getattr(execution_data, "control_kind", None)),
            review_result=clean(getattr(execution_data, "review_result", None)),
            report_types=report_types,
            subjects=subjects,
            class_groups=class_groups,
            parallel_classes=parallel_classes,
            teacher_id=teacher_id,
            teacher_ids=teacher_ids,
            report_teacher_ids=report_teacher_ids,
            school_class_ids=[str(value) for value in parameters.get("selected_class_ids", [])],
            algorithm_revision=int(parameters.get("revision") or 0),
            report_areas=list(parameters.get("report_areas") or []),
            report_areas_mode=bool(parameters.get("report_areas_mode")),
            report_area_exclusions=list(parameters.get("report_area_exclusions") or []),
            generated_reports_json=json.dumps(
                list(grouped.values()),
                ensure_ascii=False,
            ),
        )


@dataclass(slots=True)
class CurrentDraftDTO:
    """
    Краткое состояние текущего черновика выполнения задачи.
    """

    exists: bool = False
    document_id: int | None = None
