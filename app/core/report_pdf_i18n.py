"""PDF-local language context, independent of later interface language changes."""
from app.core.i18n import normalize_language,resolve_language,translate
from app.core.i18n_messages import N_

DOCUMENT_LANGUAGE_ERROR = N_('Выберите русский или казахский язык документа.')


def select_document_language(value, saved=None, fallback='ru'):
    if value is not None and str(value).strip():
        language=normalize_language(str(value))
        if language is None:raise ValueError(DOCUMENT_LANGUAGE_ERROR)
        return language
    return normalize_language(saved) or normalize_language(fallback) or 'ru'


def saved_report_language(report):
    data=getattr(report,'criteria_scores',None) if report is not None else None
    return data.get('document_language') if isinstance(data,dict) else None


def report_pdf_context(request,report,document=None):
    from app.core.report_forms_ui_messages import BUILTIN_REPORT_FORM_MESSAGES
    language=select_document_language(None,saved_report_language(report),resolve_language(request))
    def field(name):
        return document.get(name) if isinstance(document,dict) else getattr(document,name,None)
    mode=field('template_mode')
    standard=(document is not None and field('custom_template_id') is None
              and getattr(mode,'value',mode)!='custom')
    def text(value):return translate(value,language)
    def schema_text(value):
        return text(value) if standard and value in BUILTIN_REPORT_FORM_MESSAGES else value
    def level_text(value):
        labels={'Жоғары':'Высокий уровень','Орта':'Средний уровень','Төмен':'Низкий уровень'}
        return text(labels[value]) if value in labels else value
    def criterion_text(criterion,fallback):
        if isinstance(criterion,dict):
            bilingual=criterion.get('label_ru' if language=='ru' else 'label_kz')
            if criterion.get('label_ru') and bilingual:return bilingual
        return schema_text(fallback)
    return dict(pdf_language=language,pdf_text=text,pdf_schema_text=schema_text,
                pdf_level_text=level_text,pdf_criterion_text=criterion_text)
