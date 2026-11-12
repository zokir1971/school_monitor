"""Explicit UI-only strings for JavaScript. No user content is translated."""
from app.core.i18n_messages import N_
WEB_MESSAGES = {
    "save": N_("Сохранить"), "cancel": N_("Отмена"), "loading": N_("Загрузка…"),
    "error": N_("Произошла ошибка"), "select_region": N_("— выберите область —"),
    "select_district": N_("— выберите район —"), "select_school": N_("— выберите школу —"),
    "first_region": N_("— сначала выберите область —"),
    "first_district": N_("— сначала выберите район —"),
}
