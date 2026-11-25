"""One scoped aggregate read per export, independent of school count."""
from sqlalchemy import select, func, cast, String

from app.modules.assessment.models import Assessment, AssessmentQualitySummary
from app.modules.assessment.models_diagnostic_sessions import DiagnosticSubject
from app.modules.assessment.repositories.assessment_name_columns import title_column
from app.modules.assessment.repositories.knowledge_quality_analytics_repo import KnowledgeQualityAnalyticsRepo
from app.modules.org.governance import governance_filter
from app.modules.org.models import School

MAX_SCHOOL_ROWS = 50000


async def school_work_rows(db, *, region_id, academic_year_start, subject_id=None,
                           grade_level=None, work_key=None, checkpoint='', governance=''):
    level = governance_filter(governance)
    if not region_id or region_id <= 0 or academic_year_start is None:
        return []
    q, a = AssessmentQualitySummary, Assessment
    work = func.coalesce(a.diagnostic_subject_id, -a.id)
    district = func.coalesce(q.district_id_snapshot, School.district_id)
    stmt = (select(work.label('logical_id'), School.id.label('school_id'),
                   School.name.label('school_name'), School.governance_level,
                   School.district_id.label('location_district_id'),
                   district.label('district_id'),
                   func.min(title_column()).label('work_title'),
                   func.min(cast(q.checkpoint_snapshot, String)).label('checkpoint'),
                   func.min(DiagnosticSubject.session_id).label('session_id'),
                   *KnowledgeQualityAnalyticsRepo._aggregate_columns())
            .select_from(q).join(a, (a.id == q.assessment_id) & (a.school_id == q.school_id))
            .join(School, School.id == q.school_id)
            .outerjoin(DiagnosticSubject, DiagnosticSubject.id == a.diagnostic_subject_id)
            .where(q.region_id_snapshot == region_id,
                   q.academic_year_start_snapshot == academic_year_start))
    if subject_id is not None:
        stmt = stmt.where(q.subject_id == subject_id)
    if grade_level is not None:
        stmt = stmt.where(q.grade_level_snapshot == grade_level)
    if level:
        stmt = stmt.where(School.governance_level == level)
    if checkpoint == 'other':
        stmt = stmt.where(q.checkpoint_snapshot.is_(None))
    elif checkpoint in ('baseline', 'quarter_1', 'quarter_2', 'quarter_3', 'quarter_4', 'final'):
        stmt = stmt.where(q.checkpoint_snapshot == checkpoint)
    elif checkpoint:
        return []
    if work_key not in (None, 'all'):
        stmt = KnowledgeQualityAnalyticsRepo._apply_work_filter(stmt, work_key)
    stmt = (stmt.group_by(work, School.id, School.name, School.governance_level, School.district_id, district)
            .order_by(func.min(KnowledgeQualityAnalyticsRepo._checkpoint_rank()),
                      func.max(a.completed_at).asc().nullslast(), work, School.name, School.id, district)
            .limit(MAX_SCHOOL_ROWS + 1))
    rows = list((await db.execute(stmt)).mappings())
    if len(rows) > MAX_SCHOOL_ROWS:
        raise ValueError(f'Уточните фильтры: более {MAX_SCHOOL_ROWS} строк школ. / Сүзгілерді нақтылаңыз: {MAX_SCHOOL_ROWS} мектеп жолынан артық.')
    return rows
