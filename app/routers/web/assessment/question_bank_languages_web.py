"""Author workspace for two language versions of one QuestionBankItem."""
from uuid import uuid4
from fastapi import APIRouter,Depends,Request,HTTPException
from fastapi.responses import RedirectResponse
from app.db.session import get_db
from app.modules.users.deps import require_teacher_workspace
from app.modules.assessment.enums import QuestionBankItemStatus
from app.modules.assessment.services.bilingual_question_views import localized_view
from app.modules.assessment.repositories.question_bank_repo import QuestionBankRepo
from app.modules.assessment.helpers.bilingual_question_contract import source_payload,translation_fields,fingerprint,target_language,get_value,code,make_variant
from app.modules.assessment.services.bilingual_question_service import save_variant,get_variant
from app.modules.assessment.helpers.translation_editor import build_translation_editor
from app.modules.assessment.repositories.question_translation_request_repo import QuestionTranslationRequestRepo as TranslationRequests
from app.modules.assessment.services.bilingual_translation_service import request_translation
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router=APIRouter(prefix='/teacher/question-bank/items',tags=['question-bank-languages'])

async def own_item(db,item_id,user_id):
    item=await QuestionBankRepo.get_aggregate_by_id(db,item_id=item_id)
    if item is None or item.created_by_user_id!=user_id:raise HTTPException(404,'Задание или ресурс не найдены либо недоступны.')
    if code(item.language) not in ['ru','kk']:raise HTTPException(422,'Двуязычная версия доступна для русского и казахского языков.')
    return item

async def workspace(request,db,user,item,*,values=None,error=None,status_code=200):
    variant=await get_variant(db,item);payload=source_payload(item);editable=translation_fields(payload,item.question_type)
    translation_busy=False
    if error is None:
        error={'source_changed':'Исходное задание изменилось. Сверьте и сохраните перевод заново.',
               'invalid':'Состав полей перевода изменился. Обновите страницу.',
               'readonly':'Перевод можно менять только в черновике или после отклонения.'}.get(request.query_params.get('translation_notice'))
    if values is None and (variant is None or variant.source_fingerprint!=fingerprint(item)) and item.status in [QuestionBankItemStatus.DRAFT,QuestionBankItemStatus.REJECTED]:
        job=await TranslationRequests.get(db,item_id=item.id,source_hash=fingerprint(item),language=target_language(item.language),user_id=user.id)
        if job is not None:
            if job['status']=='proposed':values=job['values_json']
            elif job['status']=='running' and not job['expired']:
                translation_busy=True
            else:
                error=error or ('Исходное задание изменилось. Сверьте и сохраните перевод заново.' if job['error_code']=='source_changed' else 'Не удалось получить перевод AI. Повторите запрос или заполните перевод вручную.')
    proposed=None
    if values is not None:
        try:proposed=make_variant(payload,item.question_type,values)
        except ValueError:pass
    rows=[]
    for index,(path,text) in enumerate(editable):
        value=''
        if variant is not None:
            try:value=get_value(variant.payload,path)
            except (KeyError,IndexError,TypeError):pass
        if values is not None:value=values.get(f'f{index}','')
        rows.append(dict(name=f'f{index}',source=text,value=value,number=index+1))
    return render(templates,request,'teacher/assessment/question_bank/languages.html',dict(user=user,item=item,
        source_view=localized_view(item,payload,code(item.language)),target_view=localized_view(item,proposed,target_language(item.language)) if proposed is not None else (localized_view(item,variant.payload,variant.language) if variant is not None else None),target_language=target_language(item.language),rows=rows,
        editor_groups=build_translation_editor(payload,item.question_type,{row['name']:row['value'] for row in rows}),
        translation_busy=translation_busy,translation_attempt_token=uuid4().hex,source_hash=fingerprint(item),stale=variant is not None and variant.source_fingerprint!=fingerprint(item),
        saved=variant is not None and values is None,pending=values is not None,readonly=item.status not in [QuestionBankItemStatus.DRAFT,QuestionBankItemStatus.REJECTED],error=error),status_code=status_code)

@router.get('/{item_id}/languages',name='teacher_question_languages')
async def language_page(request:Request,item_id:int,db=Depends(get_db),user=Depends(require_teacher_workspace)):
    return await workspace(request,db,user,await own_item(db,item_id,user.id))

@router.post('/{item_id}/languages',name='teacher_question_languages_save')
async def language_save(request:Request,item_id:int,db=Depends(get_db),user=Depends(require_teacher_workspace)):
    item=await own_item(db,item_id,user.id);form=await request.form()
    values={key:value for key,value in form.items() if key.startswith('f') and key[1:].isdigit()}
    try:
        await save_variant(db,item,user_id=user.id,source_hash=str(form.get('source_hash','')),values=values)
        await db.commit()
    except (ValueError,PermissionError) as exc:
        await db.rollback();await db.refresh(user);item=await own_item(db,item_id,user.id)
        return await workspace(request,db,user,item,values=values,error=str(exc),status_code=400)
    except Exception:
        await db.rollback();raise
    return RedirectResponse(request.url_for('teacher_question_languages',item_id=item_id),status_code=303)

@router.post('/{item_id}/languages/ai',name='teacher_question_languages_ai')
async def language_ai(request:Request,item_id:int,db=Depends(get_db),user=Depends(require_teacher_workspace)):
    item=await own_item(db,item_id,user.id)
    form=await request.form();user_id=user.id
    notice=None
    try:
        await request_translation(db,item,user_id=user_id,source_hash=str(form.get('source_hash','')),
            attempt_token=str(form.get('translation_attempt_token','')))
    except (ValueError,PermissionError) as exc:
        await db.rollback()
        notice=('source_changed' if str(exc).startswith('Исходное') else 'readonly' if str(exc).startswith('Перевод можно') else 'invalid')
    url=request.url_for('teacher_question_languages',item_id=item_id)
    if notice:url=url.include_query_params(translation_notice=notice)
    return RedirectResponse(url,status_code=303)



@router.get('/{item_id}/languages/ai',name='teacher_question_languages_ai_return', dependencies=[Depends(require_teacher_workspace)])
async def language_ai_return(request:Request,item_id:int):
    # Navigation only. The destination enforces ownership. No AI call.
    return RedirectResponse(request.url_for('teacher_question_languages',item_id=item_id),status_code=303)
