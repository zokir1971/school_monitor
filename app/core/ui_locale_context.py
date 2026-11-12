"""Request-local locale for data labels, never a process-wide language."""
from contextvars import ContextVar
ui_locale=ContextVar('ui_locale',default='ru')
