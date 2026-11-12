"""A variant is edited with the source row locked; one task owns the review status."""
from sqlalchemy import select
from app.modules.assessment.models import QuestionBankItem,QuestionBankLanguageVariant
from app.modules.assessment.enums import QuestionBankItemStatus
from app.modules.assessment.helpers.bilingual_question_contract import FIELDS,source_payload,fingerprint,target_language,make_variant,assert_variant_contract,code
from app.modules.assessment.services.assessment_question_validation_service import AssessmentQuestionValidationService

async def get_variant(db,item):
    return await db.get(QuestionBankLanguageVariant,(item.id,target_language(item.language)))

def validate_payload(item,payload):
    assert_variant_contract(source_payload(item),payload,item.question_type)
    AssessmentQuestionValidationService.validate_authoring(question_type=item.question_type,
        content=payload['content'],answer_key=payload['answer_key'],grading_settings=payload['grading_settings'],max_score=item.max_score)

async def require_bilingual_ready(db,item,expected_status):
    if not getattr(item,'requires_bilingual',False) or code(item.language) not in ['ru','kk']:return
    # Serializes translation edits with submission/approval, including stale source checks.
    await db.execute(select(QuestionBankItem.__table__.c.id).where(QuestionBankItem.__table__.c.id==item.id).with_for_update())
    await db.refresh(item,attribute_names=[*FIELDS,'subject_id','grade_level','quarter','question_type','difficulty','max_score','language','status','requires_bilingual','objectives'])
    if item.status!=expected_status:raise ValueError('Статус задания изменился. Обновите страницу.')
    variant=await get_variant(db,item)
    if variant is None:raise ValueError('Сохраните русскую и казахскую версии перед отправкой на проверку.')
    if variant.source_fingerprint!=fingerprint(item):raise ValueError('Исходное задание изменилось. Сверьте и сохраните перевод заново.')
    validate_payload(item,variant.payload)

async def save_variant(db,item,*,user_id,source_hash,values):
    if item.created_by_user_id!=user_id:raise PermissionError('Нет доступа к переводу задания.')
    await db.execute(select(QuestionBankItem.__table__.c.id).where(QuestionBankItem.__table__.c.id==item.id).with_for_update())
    await db.refresh(item,attribute_names=[*FIELDS,'subject_id','grade_level','quarter','question_type','difficulty','max_score','language','status','requires_bilingual','objectives'])
    if item.status not in [QuestionBankItemStatus.DRAFT,QuestionBankItemStatus.REJECTED]:raise ValueError('Перевод можно менять только в черновике или после отклонения.')
    if fingerprint(item)!=source_hash:raise ValueError('Исходное задание изменилось. Сверьте и сохраните перевод заново.')
    payload=make_variant(source_payload(item),item.question_type,values);validate_payload(item,payload)
    variant=await get_variant(db,item)
    if variant is None:
        variant=QuestionBankLanguageVariant(item_id=item.id,language=target_language(item.language));db.add(variant)
    variant.payload=payload;variant.source_fingerprint=source_hash;variant.edited_by_user_id=user_id
    item.requires_bilingual=True;item.status=QuestionBankItemStatus.DRAFT
    await db.flush()
    return variant
