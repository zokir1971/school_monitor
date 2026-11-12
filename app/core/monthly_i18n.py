"""Known monthly planning UI feedback only; task texts remain data."""
from app.core.i18n import resolve_language,translate
from app.core.monthly_ui_messages import MONTHLY_SYSTEM_MESSAGES
from app.core.planning_i18n import planning_message


def monthly_message_text(request,value):
    if isinstance(value,str) and value in MONTHLY_SYSTEM_MESSAGES:
        return translate(value,resolve_language(request))
    return planning_message(request,value)
