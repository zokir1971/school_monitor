"""Bounded school/checkpoint aggregates for a regional dynamics workbook."""
from sqlalchemy import select,func,case
from app.modules.assessment.models import AssessmentQualitySummary as Q
from app.modules.assessment.enums import AssessmentCheckpoint
from app.modules.assessment.repositories.knowledge_quality_dynamics_repo import KnowledgeQualityDynamicsRepo
from app.modules.org.models import School
from app.modules.org.governance import governance_filter

MAX_POINT_ROWS=50000


async def school_points(db,*,region_id,academic_year_start,subject_id=None,grade_level=None,governance=''):
    level=governance_filter(governance)
    district=func.coalesce(Q.district_id_snapshot,School.district_id)
    stmt=(select(School.id.label('school_id'),School.name.label('school_name'),School.governance_level,
                 School.district_id.label('location_district_id'),district.label('district_id'),
                 Q.checkpoint_snapshot.label('checkpoint'),*KnowledgeQualityDynamicsRepo._aggregate_columns())
          .select_from(Q).join(School,School.id==Q.school_id)
          .where(Q.region_id_snapshot==region_id,Q.academic_year_start_snapshot==academic_year_start,
                 Q.checkpoint_snapshot.is_not(None)))
    if subject_id is not None:stmt=stmt.where(Q.subject_id==subject_id)
    if grade_level is not None:stmt=stmt.where(Q.grade_level_snapshot==grade_level)
    if level:stmt=stmt.where(School.governance_level==level)
    rank=case(*[(Q.checkpoint_snapshot==item,index)for index,item in enumerate(AssessmentCheckpoint)],else_=99)
    stmt=(stmt.group_by(School.id,School.name,School.governance_level,School.district_id,district,Q.checkpoint_snapshot)
          .order_by(School.name,School.id,district,rank).limit(MAX_POINT_ROWS+1))
    rows=list((await db.execute(stmt)).mappings())
    if len(rows)>MAX_POINT_ROWS:
        raise ValueError(f'Уточните фильтры: более {MAX_POINT_ROWS} строк динамики. / Сүзгілерді нақтылаңыз: {MAX_POINT_ROWS} динамика жолынан артық.')
    return rows
