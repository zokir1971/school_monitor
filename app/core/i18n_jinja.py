import re
from functools import lru_cache
from jinja2 import pass_context
from jinja2.filters import do_tojson
from jinja2.utils import htmlsafe_json_dumps
from app.core.render_locale import _active_locale
from app.core.i18n import SUPPORTED_LANGUAGES, catalog, resolve_language, normalize_language, translate


def install_i18n(environment):
    @pass_context
    def ui_language(context):
        snapshot = _active_locale.get()
        if snapshot is not None and snapshot.matches(context):
            return snapshot.language
        language = resolve_language(context["request"], context.get("user"))
        context["request"].state.ui_language = language
        return language

    @pass_context
    def gettext(context, message, **values):
        snapshot = _active_locale.get()
        if snapshot is not None and snapshot.matches(context):
            text = snapshot.gettext(message)
        else:
            language = ui_language(context)
            text = translate(message, language)
        return text % values if values else text

    @pass_context
    def ngettext(context, singular, plural, n, **values):
        text = catalog(ui_language(context)).ngettext(singular, plural, n)
        return text % dict(values, n=n)

    @pass_context
    def language_return_url(context):
        from app.core.ui_language_return import language_read_url
        request = context["request"]
        if context.get('ui_return_url'):
            return language_read_url(request,context['ui_return_url'])
        path = request.url.path
        bank_action = re.fullmatch(r"(/teacher/assessment/from-bank/[0-9]+)/(?:add|remove/[0-9]+)/?", path)
        if bank_action:
            path = bank_action.group(1)
        translation_action = re.fullmatch(r"(/teacher/question-bank/items/[0-9]+/languages)/ai/?", path)
        if translation_action:
            path = translation_action.group(1)
        if path.rstrip("/") == "/register-admin/preview":
            return language_read_url(request,"/register-admin")
        return language_read_url(request,path + (("?" + request.url.query) if request.url.query else ""))

    @pass_context
    def user_role_label(context, value):
        code = getattr(value, "value", value)
        labels = {"superuser": "Суперадминистратор", "region_admin": "Администратор области",
                  "district_admin": "Администратор района", "school_admin": "Администратор школы",
                  "teacher": "Учитель", "school_staff": "Сотрудник школы"}
        return gettext(context, labels.get(str(code).lower(), str(code)))

    @lru_cache(maxsize=2)
    def _ui_messages_for_language(language):
        from app.core.i18n_web_messages import WEB_MESSAGES
        from app.core.question_bank_ui_messages import QB_WEB_MESSAGES
        from app.core.assessment_ui_messages import ASSESSMENT_WEB_MESSAGES
        from app.core.education_ui_messages import EDUCATION_WEB_MESSAGES
        from app.core.expert_ui_messages import EXPERT_WEB_MESSAGES
        from app.core.staff_ui_messages import STAFF_WEB_MESSAGES
        from app.core.planning_ui_messages import PLANNING_WEB_MESSAGES
        from app.core.monthly_ui_messages import MONTHLY_WEB_MESSAGES
        from app.core.execution_ui_messages import EXECUTION_WEB_MESSAGES
        from app.core.reports_ui_messages import REPORTS_WEB_MESSAGES
        from app.core.report_forms_ui_messages import REPORT_FORMS_WEB_MESSAGES
        from app.core.template_constructor_ui_messages import CONSTRUCTOR_WEB_MESSAGES
        return {key: catalog(language).gettext(message) for key, message in (WEB_MESSAGES | QB_WEB_MESSAGES | ASSESSMENT_WEB_MESSAGES | EDUCATION_WEB_MESSAGES | EXPERT_WEB_MESSAGES | STAFF_WEB_MESSAGES | PLANNING_WEB_MESSAGES | MONTHLY_WEB_MESSAGES | EXECUTION_WEB_MESSAGES | REPORTS_WEB_MESSAGES | REPORT_FORMS_WEB_MESSAGES | CONSTRUCTOR_WEB_MESSAGES).items()}


    @pass_context
    def ui_messages(context):
        # Static UI strings only. A fresh dictionary prevents mutation from
        # leaking to another request; user-entered text is never cached here.
        return _ui_messages_for_language(ui_language(context)).copy()

    @lru_cache(maxsize=2)
    def _ui_payload_json_for_language(language):
        # Immutable application UI strings only: never request or school data.
        # Same serializer and script escaping as the default Jinja tojson filter.
        return htmlsafe_json_dumps(
            {"language": language, "messages": _ui_messages_for_language(language)},
            sort_keys=True,
        )

    @pass_context
    def ui_i18n_json(context):
        environment = context.environment
        # Respect custom globals, JSON policies and replacement tojson filters.
        # Those paths retain per-render construction and serialization.
        if (context.resolve("ui_language") is ui_language
                and context.resolve("ui_messages") is ui_messages
                and environment.filters.get("tojson") is do_tojson
                and environment.policies["json.dumps_function"] is None
                and environment.policies["json.dumps_kwargs"] == {"sort_keys": True}):
            return _ui_payload_json_for_language(ui_language(context))
        payload = {
            "language": context.call(context.resolve("ui_language")),
            "messages": context.call(context.resolve("ui_messages")),
        }
        return environment.call_filter("tojson", payload, context=context)

    environment.globals["ui_i18n_json"] = ui_i18n_json

    @lru_cache(maxsize=2)
    def _month_labels_for_language(language):
        from app.core.planning_period import MONTH_NAMES_KZ
        return {key: catalog(language).gettext(value) for key, value in MONTH_NAMES_KZ.items()}

    @pass_context
    def qb_subject_name(context, obj):
        def field(name):
            return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
        fields = ("subject_name_ru", "subject_name_kz") if ui_language(context) == "ru" else ("subject_name_kz", "subject_name_ru")
        return next((field(name) for name in (*fields, "subject_name", "subject_code") if field(name)), "—")

    @pass_context
    def assessment_subject_name(context, obj):
        def field(name):
            return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
        order = ("name_ru", "name_kz") if ui_language(context) == "ru" else ("name_kz", "name_ru")
        return next((field(name) for name in (*order, "subject_name", "name") if field(name)), "ID " + str(field("id") or ""))

    @pass_context
    def assessment_error(context, message):
        from app.core.assessment_i18n import assessment_error_message
        return assessment_error_message(context["request"], message, 400)

    @pass_context
    def assessment_enum_label(context, value):
        label = getattr(value, "label_kz", None)
        return gettext(context, label or str(getattr(value, "value", value)))

    @pass_context
    def education_labels(context, labels):
        return {key: gettext(context, value) for key, value in labels.items()}

    @pass_context
    def expert_specialty_name(context, obj):
        def field(name):
            return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
        ru = field("name_ru") or field("specialty_name") or field("name")
        kk = field("name_kz") or field("specialty_name_kz")
        name = (kk or ru) if ui_language(context) == "kk" else (ru or kk)
        return name or gettext(context, "Требуется настройка")

    @pass_context
    def expert_policy_name(context, objects, object_id):
        obj = next((obj for obj in objects if obj.id == object_id), None)
        return assessment_subject_name(context, obj) if obj is not None else str(object_id)

    @pass_context
    def expert_standard_label(context, value):
        # Only canonical choices are UI labels; free-form user data stays as entered.
        known = {"педагог", "педагог-модератор", "педагог-сарапшы",
                 "педагог-зерттеуші", "педагог-шебер", "Жоғары"}
        return gettext(context, value) if value in known else value

    @pass_context
    def staff_position_label(context, value):
        from app.core.staff_ui_messages import STAFF_POSITION_MESSAGES
        normalized = (value or "").strip().lower()
        return gettext(context, normalized) if normalized in STAFF_POSITION_MESSAGES else value

    @pass_context
    def staff_role_label(context, role):
        if getattr(role, "full_ru", None) and ui_language(context) == "ru":
            return role.full_ru
        label = getattr(role, "label_kz", None)
        return gettext(context, label) if label else str(getattr(role, "value", role))

    @pass_context
    def staff_role_options(context, options):
        from app.modules.planning.enums import ResponsibleRole
        language = ui_language(context)
        result = []
        for option in options:
            try:
                label = ResponsibleRole(option["value"]).option_label(language)
            except ValueError:
                label = gettext(context, option["label_kz"])
            result.append(dict(option, label_kz=label))
        return result

    @pass_context
    def responsible_role_option_label(context, value):
        from app.modules.planning.enums import ResponsibleRole
        try:
            return ResponsibleRole(value).option_label(ui_language(context))
        except ValueError:
            return str(value)

    @pass_context
    def staff_flash(context, kind, value=None):
        from app.core.staff_i18n import staff_message
        request = context["request"]
        value = value or request.query_params.get(kind)
        return staff_message(request, value) if value else ""

    @pass_context
    def planning_status_label(context, value):
        code = str(getattr(value, "value", value))
        labels = {"draft": "Жоба", "active": "Белсенді", "archived": "Мұрағатталған"}
        return gettext(context, labels.get(code, code))

    @pass_context
    def planning_period(context, row, current_month=None):
        from app.core.planning_period import format_row11_period, MONTH_NAMES_KZ
        # Prepared free-form display text and legacy deadlines are plan data.
        if getattr(row, "period_text", None):
            return str(row.period_text)
        months = _month_labels_for_language(ui_language(context)).copy()
        text = format_row11_period(row, current_month=current_month, month_names=months)
        period = str(getattr(getattr(row, "period_type", None), "value", getattr(row, "period_type", None)))
        if period in {"quarter", "all_year", "monthly"}:
            return gettext(context, text)
        if period in {"month", "months"}:
            for prefix in ("Ай: ", "Айлар: "):
                if text.startswith(prefix) and any(name in text[len(prefix):] for name in months.values()):
                    return gettext(context, prefix.rstrip()) + " " + text[len(prefix):]
        return text

    environment.filters["planning_period"] = planning_period
    @pass_context
    def planning_error(context, message):
        from app.core.planning_i18n import planning_message
        return planning_message(context["request"], message)

    @pass_context
    def monthly_message(context, value):
        from app.core.monthly_i18n import monthly_message_text
        return monthly_message_text(context["request"], value)

    @pass_context
    def monthly_assignment_label(context, item):
        if not item.has_primary_assignee:
            return gettext(context, "Назначить")
        if item.co_executor_count > 0:
            return gettext(context, "Назначено (+{count})").format(count=item.co_executor_count)
        return gettext(context, "Назначено")

    @pass_context
    def execution_error(context, value):
        from app.core.execution_i18n import execution_message
        return execution_message(context["request"], value)

    @pass_context
    def report_target_label(context, value):
        labels = {"teacher": "Учитель", "class": "Класс", "subject": "Предмет",
                  "teacher_subject_class": "Учитель / класс / предмет", "documentation": "Документация"}
        return gettext(context, labels.get(value, value or "Объект"))

    @pass_context
    def reports_feedback(context, value):
        from app.core.reports_i18n import reports_message
        return reports_message(context["request"], value)

    @pass_context
    def report_form_label(context, value):
        from app.core.report_forms_ui_messages import BUILTIN_REPORT_FORM_MESSAGES
        document = context.get("document")
        def field(name):
            return document.get(name) if isinstance(document, dict) else getattr(document, name, None)
        mode = field("template_mode")
        document_custom = (field("custom_template_id") is not None
                           or getattr(mode, "value", mode) == "custom")
        # A saved snapshot takes precedence over a template_id in the URL.
        custom = document_custom if document is not None and field("schema_json") else (
            context.get("template_id") is not None or document_custom)
        if not custom and value and value in BUILTIN_REPORT_FORM_MESSAGES:
            return gettext(context, value)
        return value

    @pass_context
    def report_score_level_label(context, value):
        labels = {"Жоғары": "Высокий уровень", "Орта": "Средний уровень", "Төмен": "Низкий уровень"}
        return gettext(context, labels[value]) if value in labels else value or "—"

    @pass_context
    def completion_feedback(context, value):
        from app.core.report_completion_i18n import completion_message
        return completion_message(value, ui_language(context))

    @pass_context
    def completion_review_places(context, value):
        from app.core.report_completion_i18n import review_places_label
        return review_places_label(value, ui_language(context))

    @pass_context
    def verify_report_label(context, result):
        from app.core.report_completion_i18n import VERIFY_REPORT_LABELS
        code = result.get('report_type')
        label = result.get('report_label')
        canonical = VERIFY_REPORT_LABELS.get(code)
        # An explicitly supplied custom label remains authored data.
        if canonical and (not label or label == canonical):
            return gettext(context, canonical)
        return label or code or '—'

    @pass_context
    def verify_detail_label(context, value):
        from app.core.report_completion_i18n import BUILTIN_VERIFY_DETAIL_LABELS
        return gettext(context, value) if value in BUILTIN_VERIFY_DETAIL_LABELS else value

    @pass_context
    def verify_feedback(context, value):
        from app.core.report_completion_i18n import verification_message
        return verification_message(value, ui_language(context))

    environment.globals.update(completion_feedback=completion_feedback,
        completion_review_places=completion_review_places, verify_report_label=verify_report_label,
        verify_detail_label=verify_detail_label, verify_feedback=verify_feedback)

    @pass_context
    def review_place_columns(context):
        from app.modules.planning.enums import ReviewPlace
        language = ui_language(context)
        return [dict(value=p.value, field=p.value + '_count', label=p.display_label(language)) for p in ReviewPlace]

    environment.globals['review_place_columns'] = review_place_columns

    @pass_context
    def review_result_label(context, value):
        from app.core.review_results_i18n import result_label
        return result_label(value, ui_language(context))

    @pass_context
    def review_protocol_label(context, value):
        from app.core.review_results_i18n import protocol_label
        return protocol_label(value, ui_language(context))

    @pass_context
    def review_result_error(context, value):
        from app.core.review_results_i18n import result_message
        return result_message(value, ui_language(context))

    environment.globals.update(review_result_label=review_result_label,
        review_protocol_label=review_protocol_label, review_result_error=review_result_error)

    @pass_context
    def task_review_error(context, value):
        from app.core.task_review_i18n import task_review_message
        return task_review_message(value, ui_language(context))

    @pass_context
    def task_review_expected_result(context, value):
        from app.core.task_review_i18n import TASK_REVIEW_EXPECTED_RESULTS
        return gettext(context, value) if value in TASK_REVIEW_EXPECTED_RESULTS else value or '—'

    environment.globals.update(task_review_error=task_review_error,
        task_review_expected_result=task_review_expected_result)

    @pass_context
    def method_association_name(context, value):
        from app.core.method_associations_i18n import association_name
        return association_name(value, ui_language(context))

    @pass_context
    def method_association_error(context, value):
        from app.core.method_associations_i18n import association_error
        return association_error(value, ui_language(context))

    environment.globals.update(method_association_name=method_association_name,
        method_association_error=method_association_error)

    @pass_context
    def super_planning_message(context, value):
        from app.core.super_planning_i18n import super_planning_feedback
        return super_planning_feedback(value, ui_language(context))

    environment.globals.update(super_planning_message=super_planning_message)

    @pass_context
    def schools_feedback(context, value):
        from app.core.schools_i18n import school_feedback
        return school_feedback(value, ui_language(context))

    environment.globals.update(schools_feedback=schools_feedback)

    @pass_context
    def bilingual_feedback(context, value):
        from app.core.bilingual_ui_messages import BILINGUAL_MESSAGES
        source=value if value in BILINGUAL_MESSAGES else 'Не удалось сохранить перевод. Проверьте все поля и исходное задание.'
        return gettext(context, source)

    environment.globals.update(bilingual_feedback=bilingual_feedback)

    @pass_context
    def bank_feedback(context, value):
        from app.core.assessment_bank_ui_messages import BANK_MESSAGES
        return gettext(context, value if value in BANK_MESSAGES else 'Не удалось изменить Assessment. Обновите страницу и повторите действие.')

    environment.globals.update(bank_feedback=bank_feedback)

    @pass_context
    def question_instruction(context, value, language=None):
        from app.core.question_instructions import instruction_text
        return instruction_text(value, normalize_language(getattr(language, 'value', language)) or ui_language(context))

    environment.globals.update(question_instruction=question_instruction)



    environment.globals.update(report_form_label=report_form_label, report_score_level_label=report_score_level_label)
    environment.globals.update(report_target_label=report_target_label, reports_feedback=reports_feedback)
    environment.globals.update(execution_error=execution_error)
    environment.globals.update(monthly_message=monthly_message, monthly_assignment_label=monthly_assignment_label)
    environment.globals.update(planning_status_label=planning_status_label, planning_error=planning_error)
    environment.globals.update(staff_position_label=staff_position_label,
        staff_role_label=staff_role_label, staff_role_options=staff_role_options,
        responsible_role_option_label=responsible_role_option_label, staff_flash=staff_flash)
    environment.globals.update(expert_specialty_name=expert_specialty_name,
        expert_policy_name=expert_policy_name, expert_standard_label=expert_standard_label,
        education_labels=education_labels)
    environment.globals.update(assessment_subject_name=assessment_subject_name,
                               assessment_error=assessment_error, assessment_enum_label=assessment_enum_label,
qb_subject_name=qb_subject_name,
language_return_url=language_return_url,
                               user_role_label=user_role_label, ui_messages=ui_messages,
_=gettext, gettext=gettext, ngettext=ngettext,
                               ui_language=ui_language,
                               ui_languages=SUPPORTED_LANGUAGES)
