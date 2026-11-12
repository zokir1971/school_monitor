"""Durable orchestration; never hold an application transaction over the API call."""
import logging,re
from app.modules.assessment.helpers.bilingual_question_contract import source_payload,fingerprint,target_language,FIELDS
from app.modules.assessment.enums import QuestionBankItemStatus
from app.modules.assessment.repositories.question_translation_request_repo import QuestionTranslationRequestRepo as Requests
from app.modules.assessment.services.bilingual_question_service import get_variant,validate_payload
from app.modules.assessment.adapters.question_translation_adapter import QuestionTranslationAdapter

logger=logging.getLogger(__name__)

async def request_translation(db,item,*,user_id,source_hash,attempt_token,translator=None):
    if not isinstance(attempt_token,str) or not re.fullmatch('[0-9a-f]{32}',attempt_token):
        raise ValueError('Состав полей перевода изменился. Обновите страницу.')
    if item.created_by_user_id!=user_id:raise PermissionError('Нет доступа к переводу задания.')
    if item.status not in [QuestionBankItemStatus.DRAFT,QuestionBankItemStatus.REJECTED]:
        raise ValueError('Перевод можно менять только в черновике или после отклонения.')
    if fingerprint(item)!=source_hash:raise ValueError('Исходное задание изменилось. Сверьте и сохраните перевод заново.')
    language=target_language(item.language);item_id=item.id
    variant=await get_variant(db,item)
    # Never overwrite/retranslate a current saved human-approved version.
    if variant is not None and variant.source_fingerprint==source_hash:
        await db.rollback();return
    payload=source_payload(item);question_type=item.question_type
    params=dict(item_id=item_id,source_hash=source_hash,language=language,user_id=user_id,attempt_token=attempt_token)
    claimed=await Requests.claim(db,**params)
    await db.commit() # Commit claim before external IO; releases DB connection.
    if not claimed:return
    try:
        values,translated=await (translator or QuestionTranslationAdapter()).translate_question(payload,question_type,language)
        # Recheck source after the remote call, including objectives and status.
        await db.refresh(item,attribute_names=[*FIELDS,'subject_id','grade_level','quarter','question_type','difficulty','max_score','language','status','created_by_user_id','objectives'])
        if item.created_by_user_id!=user_id or fingerprint(item)!=source_hash or item.status not in [QuestionBankItemStatus.DRAFT,QuestionBankItemStatus.REJECTED]:
            await Requests.finish(db,**params,error_code='source_changed')
        else:
            validate_payload(item,translated)
            await Requests.finish(db,**params,values=values)
        await db.commit()
    except Exception:
        await db.rollback()
        # No raw task/answers/provider response in logs or user-facing errors.
        logger.warning('AI translation request failed; item_id=%s',item_id)
        await Requests.finish(db,**params,error_code='translation_failed')
        await db.commit()
