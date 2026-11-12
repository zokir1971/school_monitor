# app/web/web_common.py
from pathlib import Path
from fastapi.templating import Jinja2Templates
from dataclasses import asdict, is_dataclass
from app.routers.web.jinja_filters import format_row11_period, MONTH_NAMES_KZ

BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))

# ВАЖНО: автоперезагрузка шаблонов + сброс кэша
from app.core.i18n_jinja import install_i18n
install_i18n(templates.env)

templates.env.auto_reload = True
templates.env.cache = {}

templates.env.filters["row11_period"] = format_row11_period
templates.env.globals["MONTH_NAMES"] = MONTH_NAMES_KZ  # если нужно в шаблонах отдельно


def to_json_ready(value):
    if is_dataclass(value):
        return asdict(value)

    if isinstance(value, list):
        return [asdict(x) if is_dataclass(x) else x for x in value]

    return value


templates.env.filters["to_json_ready"] = to_json_ready

from app.modules.assessment.helpers.question_prose_layout import explanation_layout, part_statement_layout
templates.env.filters["explanation_layout"] = explanation_layout
templates.env.filters["part_statement_layout"] = part_statement_layout

from app.modules.assessment.helpers.question_prose_layout import matching_label
templates.env.filters["matching_label"] = matching_label

from app.modules.assessment.helpers.question_prose_layout import matching_letter
templates.env.filters["matching_letter"] = matching_letter

from app.modules.assessment.helpers.question_card_i18n import question_gettext
templates.env.globals["question_gettext"] = question_gettext

from app.modules.assessment.helpers.element_scoring import parameter_rules, form_parameters
templates.env.globals["question_parameter_rules"] = parameter_rules
templates.env.globals["question_form_parameters"] = form_parameters

from app.core.feature_access import install_feature_helpers
install_feature_helpers(templates.env)
