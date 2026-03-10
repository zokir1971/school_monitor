# app/web/web_common.py
from pathlib import Path
from fastapi.templating import Jinja2Templates
from app.routers.web.jinja_filters import format_row11_period, MONTH_NAMES_KZ

BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))

# ВАЖНО: автоперезагрузка шаблонов + сброс кэша
templates.env.auto_reload = True
templates.env.cache = {}

templates.env.filters["row11_period"] = format_row11_period
templates.env.globals["MONTH_NAMES"] = MONTH_NAMES_KZ  # если нужно в шаблонах отдельно





