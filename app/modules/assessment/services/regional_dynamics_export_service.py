"""All five sheets use one cohort and the same dynamics calculator as the page."""
from collections import defaultdict

from app.core.ui_locale_context import ui_locale
from app.modules.assessment.enums import AssessmentCheckpoint
from app.modules.assessment.repositories.regional_dynamics_export_repo import school_points
from app.modules.assessment.repositories.knowledge_quality_dynamics_repo import KnowledgeQualityDynamicsRow
from app.modules.assessment.schemas.dynamics_export_schemas import DynamicsExportDTO,DynamicsExportEntity
from app.modules.assessment.services.knowledge_quality_dynamics_service import KnowledgeQualityDynamicsService as Dynamics
from app.modules.education.repositories.subject_repo import SubjectRepo
from app.modules.org.repositories.org_lookup_repo import OrgLookupRepo
from app.modules.org.governance import governance_filter,regional_label


def points(rows):
    grouped=defaultdict(list)
    for row in rows:grouped[row['checkpoint']].append(row)
    values=[]
    for checkpoint,items in grouped.items():
        counts={key:sum(int(row[key]or 0)for row in items)for key in
                ('total_students','participated_students','grade_5_count','grade_4_count','quality_students')}
        values.append(KnowledgeQualityDynamicsRow(checkpoint=AssessmentCheckpoint(checkpoint),**counts))
    return Dynamics._build_checkpoint_points(values)


async def build(db,*,region_id,academic_year_start,subject_id=None,grade_level=None,governance=''):
    Dynamics._validate_positive_id('region_id',region_id)
    Dynamics._validate_academic_year(academic_year_start)
    Dynamics._validate_optional_positive_id('subject_id',subject_id)
    Dynamics._validate_optional_positive_id('grade_level',grade_level)
    level=governance_filter(governance)
    rows=await school_points(db,region_id=region_id,academic_year_start=academic_year_start,
                            subject_id=subject_id,grade_level=grade_level,governance=level)
    district_ids={row[key]for row in rows for key in ('district_id','location_district_id')if row[key]is not None}
    names=await OrgLookupRepo.get_district_names_by_ids(db,district_ids=tuple(district_ids))if district_ids else {}
    region_names=await OrgLookupRepo.get_region_names_by_ids(db,region_ids=(region_id,))
    region_name=region_names.get(region_id,f'ID {region_id}')
    subject_name=f'ID {subject_id}'if subject_id is not None else None
    if subject_id is not None:
        subjects=await SubjectRepo.get_active_by_ids(db,subject_ids=(subject_id,))
        if subjects:
            subject=subjects[0]
            subject_name=(subject.name_kz if ui_locale.get()=='kk'else subject.name_ru)or subject.name_kz or subject_name
    districts,schools,direct_schools=defaultdict(list),defaultdict(list),defaultdict(list)
    direct=[]
    for row in rows:
        if row['governance_level']=='region':
            direct.append(row);direct_schools[row['school_id']].append(row)
        else:
            districts[row['district_id']].append(row);schools[row['school_id']].append(row)

    def school_entities(groups):
        result=[]
        for school_id,items in groups.items():
            first=items[0]
            result.append(DynamicsExportEntity(id=school_id,name=first['school_name'],points=points(items),
                district_name=names.get(first['location_district_id'],f'ID {first["location_district_id"]}')))
        return tuple(result)

    return DynamicsExportDTO(region_name=region_name,academic_year_start=academic_year_start,
        subject_name=subject_name,grade_level=grade_level,governance=level,
        overall=DynamicsExportEntity(id=region_id,name=region_name,points=points(rows)),
        districts=tuple(DynamicsExportEntity(id=key,name=names.get(key,f'ID {key}'),points=points(items))for key,items in districts.items()),
        schools=school_entities(schools),
        regional=DynamicsExportEntity(id=region_id,name=regional_label(),points=points(direct)),
        regional_schools=school_entities(direct_schools))
