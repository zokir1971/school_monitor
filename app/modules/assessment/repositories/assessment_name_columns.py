"""SQL labels for names stored alongside existing Assessment settings."""
from sqlalchemy import func
from app.core.ui_locale_context import ui_locale
from app.modules.assessment.models import Assessment

def title_column():
    lang='kk' if ui_locale.get()=='kk' else 'ru'
    return func.coalesce(Assessment.settings['standard_name_v1'][lang].as_string(),Assessment.title)
