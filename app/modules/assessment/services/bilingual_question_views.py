"""Read-only translated DTOs; source records and review history stay unchanged."""
from dataclasses import fields,is_dataclass
from types import SimpleNamespace
from sqlalchemy import select
from app.modules.assessment.models import QuestionBankLanguageVariant
from app.modules.assessment.enums import AssessmentLanguage
from app.modules.assessment.helpers.bilingual_question_contract import code,target_language

def localized_view(item,payload,language):
    names=[f.name for f in fields(item)] if is_dataclass(item) else []
    values={name:getattr(item,name) for name in names}
    if not names:
        names=['id','subject_id','grade_level','quarter','question_type','difficulty','status','max_score','objectives']
        values={name:getattr(item,name,None) for name in names}
    values.update(payload);values['language']=AssessmentLanguage(language)
    return SimpleNamespace(**values)

async def review_variants(db,items):
    ids=[item.item_id for item in items]
    if not ids:return {}
    rows=(await db.execute(select(QuestionBankLanguageVariant).where(QuestionBankLanguageVariant.item_id.in_(ids)))).scalars().all()
    by_id={item.item_id:item for item in items}
    return {row.item_id:localized_view(by_id[row.item_id],row.payload,row.language) for row in rows if row.item_id in by_id and code(by_id[row.item_id].language) in ['ru','kk'] and row.language==target_language(by_id[row.item_id].language)}

