# app/db/__init__.py
# Регистрация моделей (Необходимо для тестирования, регистрация происходить всегда)

from app.db.base import Base  # noqa

# регистрация моделей
from app.modules.org import models as org_models  # noqa: F401
from app.modules.users import models as users_models  # noqa: F401
from app.modules.planning import models as planning_models  # noqa: F401
from app.modules.planning import models_school as planning_models_school  # noqa: F401
from app.modules.planning import models_month_plan as planning_models_month_plan  # noqa: F401
from app.modules.staff import models_staff_school as staff_models_staff_school  # noqa: F401
from app.modules.reports import models_documents as reports_models_documents  # noqa: F401
