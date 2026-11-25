from dataclasses import dataclass
from app.modules.assessment.schemas.knowledge_quality_dynamics_schemas import KnowledgeQualityCheckpointDTO


@dataclass(frozen=True,slots=True)
class DynamicsExportEntity:
    id:int
    name:str
    points:tuple[KnowledgeQualityCheckpointDTO,...]
    district_name:str=''


@dataclass(frozen=True,slots=True)
class DynamicsExportDTO:
    region_name:str
    academic_year_start:int
    subject_name:str|None
    grade_level:int|None
    governance:str
    overall:DynamicsExportEntity
    districts:tuple[DynamicsExportEntity,...]
    schools:tuple[DynamicsExportEntity,...]
    regional:DynamicsExportEntity
    regional_schools:tuple[DynamicsExportEntity,...]
