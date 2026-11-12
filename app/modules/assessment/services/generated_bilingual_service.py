"""Persist both language versions inside the generation transaction, never partial."""
from copy import deepcopy
from app.modules.assessment.models import QuestionBankLanguageVariant
from app.modules.assessment.repositories.question_bank_repo import QuestionBankRepo
from app.modules.assessment.helpers.bilingual_question_contract import fingerprint, target_language, code
from app.modules.assessment.services.bilingual_question_service import validate_payload


async def save_generated_variant(db, *, item_id, response, user_id, language):
    if code(language) not in ['ru', 'kk']:
        return
    target = target_language(language)
    if response.metadata.get('bilingual_language') != target:
        raise ValueError('The generation response must contain both RU and KZ.')
    payload = response.metadata.get('bilingual_payload')
    if not isinstance(payload, dict):
        raise ValueError('Generated translation is missing.')
    item = await QuestionBankRepo.get_aggregate_by_id(db, item_id=item_id)
    if item is None or item.created_by_user_id != user_id or code(item.status) != 'draft':
        raise ValueError('Generated draft does not match its author or state.')
    # Quarter and objective links have already been saved by the caller.
    await db.refresh(item, attribute_names=['quarter', 'objectives'])
    validate_payload(item, payload)
    if await db.get(QuestionBankLanguageVariant, (item_id, target)) is not None:
        raise ValueError('Generated translation already exists.')
    db.add(QuestionBankLanguageVariant(item_id=item_id, language=target,
        payload=deepcopy(payload), source_fingerprint=fingerprint(item), edited_by_user_id=user_id))
    item.requires_bilingual = True
    await db.flush()


async def save_generated_variants(db, *, item_ids, response, user_id, language):
    if code(language) not in ['ru', 'kk']:
        return
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.modules.assessment.models import QuestionBankItem, QuestionBankItemObjective
    target = target_language(language)
    payloads = response.metadata.get('bilingual_payloads')
    if payloads is None and len(item_ids) == 1:
        payloads = [response.metadata.get('bilingual_payload')]
    if response.metadata.get('bilingual_language') != target or not isinstance(payloads, list) or len(payloads) != len(item_ids):
        raise ValueError('Generated translations are missing.')
    result = await db.execute(select(QuestionBankItem).where(QuestionBankItem.id.in_(item_ids)).options(
        selectinload(QuestionBankItem.objectives).selectinload(QuestionBankItemObjective.learning_objective)
    ).execution_options(populate_existing=True))
    items = {item.id:item for item in result.scalars().all()}
    variants = []
    for item_id, payload in zip(item_ids, payloads):
        item = items.get(item_id)
        if item is None or item.created_by_user_id != user_id or code(item.status) != 'draft':
            raise ValueError('Generated draft does not match its author or state.')
        validate_payload(item, payload)
        variants.append(QuestionBankLanguageVariant(item_id=item_id, language=target,
            payload=deepcopy(payload), source_fingerprint=fingerprint(item), edited_by_user_id=user_id))
        item.requires_bilingual = True
    db.add_all(variants)
    await db.flush()
