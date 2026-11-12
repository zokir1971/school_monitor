from app.modules.reports.repositories import assessment_report_repo as repo
from app.modules.reports.system_report_dto.report_verify_dto import ReportVerifyViewDTO
from app.modules.reports.assessment_report_types import REPORT_TYPES

class QualityVerifyHandler:
    CODE='knowledge_quality_table'

    @classmethod
    async def build(cls,db,*,report_id,document_id,total):
        doc=await repo.document_by_id(db,report_id,report_code=cls.CODE)
        if not doc or doc['id']!=document_id or getattr(doc['status'],'value',doc['status']) not in ('submitted','approved','accepted'):
            raise ValueError('Отчёт не найден / Есеп табылмады')
        data=doc['schema_json'] or {}
        return ReportVerifyViewDTO(valid=True,report_type=cls.CODE,report_label=REPORT_TYPES[cls.CODE]['title_kk'],
            report_id=report_id,document_id=document_id,signed_at=doc['submitted_at'],total=None,
            details=[{'label':'Білім беру ұйымы / Школа','value':data.get('school_name')},
                {'label':'Бақылау нысаны / Объект контроля','value':data.get('target_label')}])

class GeneralAnalysisVerifyHandler(QualityVerifyHandler):
    CODE='class_summary'
