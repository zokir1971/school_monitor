# app/db/models_documents.py (Регистрация моделей. Необходимо для тестирования, регистрация происходить всегда)

# Импортируем модели, чтобы они зарегистрировались в Base.metadata

from app.modules.org.models import Region, District, School  # noqa: F401
from app.modules.users.models import User, RegistrationCode, RegistrationCodeUse  # noqa: F401

from app.modules.planning.models import PlanTemplate, PlanDirection, PlanTemplateDirection, PlanTemplateRow4, PlanTemplateRow11  # noqa: F401
from app.modules.planning.models_school import SchoolPlan, SchoolPlanRow4, SchoolPlanRow11, SchoolPlanRow11Responsible, SchoolPlanRow11Assignee, SchoolPlanRow11ReviewPlace, SchoolPlanRow11RequiredDocument  # noqa: F401
from app.modules.planning.models_month_plan import SchoolMonthPlan, SchoolMonthPlanItem, SchoolMonthPlanItemAssignee, SchoolMonthPlanItemReviewPlace, SchoolMonthPlanItemExecution  # noqa: F401
from app.modules.staff.models_staff_school import SchoolStaffMember, SchoolStaffRole  # noqa: F401
from app.modules.reports.models_documents import TaskExecutionDocument, ReportTypeModel, TaskExecutionData, TaskExecutionDataReportType  # noqa: F401
