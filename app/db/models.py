# app/db/models.py (Регистрация моделей. Необходимо для тестирования, регистрация происходить всегда)

# Импортируем модели, чтобы они зарегистрировались в Base.metadata

from app.modules.org.models import Region, District, School  # noqa: F401
from app.modules.users.models import User, RegistrationCode, RegistrationCodeUse  # noqa: F401

from app.modules.planning.models import PlanTemplate, PlanDirection, PlanTemplateDirection, PlanTemplateRow4, PlanTemplateRow11  # noqa: F401
from app.modules.planning.models_school import SchoolPlan, SchoolPlanRow4, SchoolPlanRow11, SchoolPlanRow11Responsible, SchoolPlanRow11Assignee, SchoolPlanRow11ReviewPlace, SchoolPlanRow11RequiredDocument  # noqa: F401
from app.modules.planning.models_month_plan import SchoolMonthPlan, SchoolMonthPlanItem, SchoolMonthPlanItemAssignee, SchoolMonthPlanItemReviewPlace, SchoolMonthPlanItemExecution  # noqa: F401
from app.modules.planning.models_month_plan_notification import SchoolMonthPlanNotification  # noqa: F401
from app.modules.staff.models_staff_school import SchoolStaffMember, SchoolStaffRole  # noqa: F401
from app.modules.reports.models_documents import TaskExecutionDocument, ReportTypeModel, TaskExecutionData, TaskExecutionSelectedReport  # noqa: F401
from app.modules.reports.models_template_reports import LessonObservationReport, UserReportTemplate, CheckingNotebooksReport  # noqa: F401
from app.modules.reports.models_report_signature_token import ReportSignatureToken  # noqa: F401
from app.modules.reports.models_report_assignments import TaskSelectedReportAssignment  # noqa: F401
from app.modules.reviews.models_task_review import SchoolMethodAssociation, SchoolTaskReview, SchoolMonthPlanItemReviewResult  # noqa: F401
from app.modules.education.models import Subject, SchoolClass, SchoolStudent, SchoolStudentEnrollment, SchoolClassSubjectTeacher  # noqa: F401
from app.modules.assessment.models import Assessment, AssessmentGroup, AssessmentStudent, LearningObjective, AssessmentObjective, AssessmentResult, AssessmentObjectiveResult, AssessmentQuestion, AssessmentStudentAnswer, AssessmentTaskLink, AssessmentQualitySummary  # noqa: F401
from app.modules.assessment.models_question_bank_experts import QuestionBankExpert  # noqa: F401
from app.modules.assessment.models_teacher_ai_question_runs import TeacherAIQuestionRun  # noqa: F401
from app.modules.assessment.models_learning_objective_reference import LearningObjectiveSource, LearningObjectiveProgram, LearningObjectiveQuarter, LearningObjectiveFormulation  # noqa: F401

from app.modules.assessment.models_learning_objective_import import LearningObjectiveImportDraft  # noqa: F401

from app.modules.assessment.models_work_plans import AssessmentWorkPlan, AssessmentWorkPlanItem  # noqa: F401

from app.modules.assessment.models_work_assignments import AssessmentWorkAssignment, AssessmentWorkParticipant  # noqa: F401

from app.modules.assessment.models_diagnostic_sessions import DiagnosticSession, DiagnosticSubject, DiagnosticParticipant  # noqa: F401
from app.modules.assessment.models_diagnostic_attempts import DiagnosticAttempt  # noqa: F401
from app.modules.assessment.models_diagnostic_preparation import DiagnosticPreparation  # noqa: F401

from app.modules.users.models_recovery import AccessRecoveryGrant, AccessRecoveryAudit, AccessRecoveryLimit  # noqa: F401

from app.modules.statistics.activity_tables import activity_days, activity_state  # noqa: F401
