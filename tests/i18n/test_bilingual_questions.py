"""Bilingual contract/lifecycle checks without a production DB or AI request."""
import ast,asyncio,copy,json,sys,types,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from decimal import Decimal
from test_ui_language import PROJECT,environment,request
from app.modules.assessment.enums import AssessmentLanguage as Lang,AssessmentQuestionType as Type,QuestionBankItemStatus as Status
from app.modules.assessment.helpers.bilingual_question_contract import *
# Avoid initializing unrelated storage/configuration when importing the pure validator.
_storage=types.ModuleType('app.core.storage');_storage.__path__=[str(PROJECT/'app/core/storage')]
sys.modules.setdefault('app.core.storage',_storage)
from app.modules.assessment.services import bilingual_question_service as service
from app.modules.assessment.models import QuestionBankItem,QuestionBankLanguageVariant

def item(kind=Type.SINGLE_CHOICE):
 return NS(id=7,created_by_user_id=3,requires_bilingual=True,subject_id=2,grade_level=5,quarter=1,question_type=kind,difficulty='basic',max_score=Decimal('1'),language=Lang.RUSSIAN,status=Status.DRAFT,objectives=[NS(learning_objective_id=8)],title='Тема',text='Найдите ответ',text_segments=[{'type':'text','text':'Найдите ответ'},{'type':'latex','text':r'x\in A'}],instruction='Выберите вариант',content={'options':[{'value':'A','segments':[{'type':'text','text':'Первый вариант'}]},{'value':'B','segments':[{'type':'text','text':'Второй вариант'}]}]},answer_key={'value':'A'},grading_settings={},explanation='Объяснение',author_comment=None)
def translations(source,kind):return {f'f{i}':'Аударма '+text for i,(_,text) in enumerate(translation_fields(source,kind))}
def variant_for(value):
 payload=make_variant(source_payload(value),value.question_type,translations(source_payload(value),value.question_type))
 return NS(item_id=value.id,language='kk',payload=payload,source_fingerprint=fingerprint(value),edited_by_user_id=3)
class DB:
 def __init__(self,variant=None):self.variant=variant;self.commits=0;self.rollbacks=0;self.locks=[];self.refresh_action=None;self.review_count=0
 async def execute(self,statement):self.locks.append(str(statement));return None
 async def refresh(self,value,**kw):
  if self.refresh_action:self.refresh_action(value)
 async def get(self,model,key):return self.variant
 def add(self,value):self.variant=value
 async def flush(self):pass
 async def commit(self):self.commits+=1
 async def rollback(self):self.rollbacks+=1

def extract_function(filename,name,scope):
 tree=ast.parse((PROJECT/filename).read_text());fn=copy.deepcopy(next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name==name));fn.decorator_list=[];fn.returns=None
 for arg in fn.args.args+fn.args.kwonlyargs:arg.annotation=None
 module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]));exec(compile(module,filename,'exec'),scope);return scope[name]
class BilingualQuestionsTests(unittest.TestCase):
 def test_all_types_preserve_technical_shape(self):
  for kind in Type:
   source=source_payload(item(kind));source['content'].update(parts=[{'id':'P1','segments':[{'type':'text','text':'Решите'},{'type':'latex','text':'2+2=4'}]}],image={'type':'image','url':'/media/test.png','object_key':'protected-key'},word_bank=['слово','x+2'])
   source['grading_settings']={'criteria':[{'id':'C1','title':'Название','description':'Обоснование','max_score':1}]};source['answer_key'].update(accepted_answers=['слово','2+2'])
   before=copy.deepcopy(source);target=make_variant(source,kind,translations(source,kind));assert_variant_contract(source,target,kind)
   self.assertEqual(source,before);self.assertEqual(target['text'],target['text_segments'][0]['text']);self.assertEqual(target['content']['options'][0]['value'],'A');self.assertEqual(target['content']['parts'][0]['id'],'P1');self.assertEqual(target['content']['parts'][0]['segments'][1]['text'],'2+2=4');self.assertEqual(target['content']['image'],source['content']['image']);self.assertEqual(target['grading_settings']['criteria'][0]['max_score'],1);self.assertEqual(target['answer_key']['value'],'A')
   for bad in ['answer','points','formula','media']:
    forged=copy.deepcopy(target)
    if bad=='answer':forged['answer_key']['value']='B'
    if bad=='points':forged['grading_settings']['criteria'][0]['max_score']=2
    if bad=='formula':forged['content']['parts'][0]['segments'][1]['text']='2+2=5'
    if bad=='media':forged['content']['image']['object_key']='other-key'
    with self.assertRaises(ValueError):assert_variant_contract(source,forged,kind)
 def test_fingerprint_and_field_set(self):
  original=item();digest=fingerprint(original);edited=copy.deepcopy(original);edited.text+=' новый';self.assertNotEqual(digest,fingerprint(edited));edited=copy.deepcopy(original);edited.objectives=[NS(learning_objective_id=9)];self.assertNotEqual(digest,fingerprint(edited))
  for values in [{},{'f999':'hack'}]:
   with self.assertRaises(ValueError):make_variant(source_payload(original),original.question_type,values)
 def test_save_translation_ownership_status_and_source(self):
  value=item();db=DB();source=source_payload(value);values=translations(source,value.question_type)
  with patch.object(service,'QuestionBankLanguageVariant',side_effect=lambda **kw:NS(**kw)):
   result=asyncio.run(service.save_variant(db,value,user_id=3,source_hash=fingerprint(value),values=values))
  self.assertEqual(result.language,'kk');self.assertEqual(value.status,Status.DRAFT);self.assertTrue(value.requires_bilingual);self.assertEqual(db.commits,0);self.assertIn('FOR UPDATE',db.locks[0]);self.assertEqual(result.payload['answer_key'],value.answer_key)
  for user,status,source_hash,error in [(4,Status.DRAFT,fingerprint(value),PermissionError),(3,Status.READY,fingerprint(value),ValueError),(3,Status.DRAFT,'stale',ValueError)]:
   value.status=status
   with self.assertRaises(error):asyncio.run(service.save_variant(DB(),value,user_id=user,source_hash=source_hash,values=values))
 def test_submit_and_approve_share_one_lifecycle(self):
  value=item();db=DB();reviews=[]
  async def load(db,**kw):return value
  async def add_review(db,review):reviews.append(review);review.id=len(reviews);return review
  cls=NS(_get_aggregate_or_raise=load,_validate_item_for_review=lambda v:service.validate_payload(v,source_payload(v)),_require_status=lambda v,expected: self.assertEqual(v.status,expected),_validate_reviewer_user_id=lambda v:None,_normalize_optional_text=lambda v:v)
  scope=dict(QuestionBankItemStatus=Status,QuestionBankReviewDecision=NS(APPROVED='approved',REJECTED='rejected'),QuestionBankItemReview=lambda **kw:NS(**kw),QuestionBankReviewCreateResult=lambda **kw:NS(**kw),QuestionBankRepo=NS(flush=lambda db:db.flush(),add_review=add_review))
  path='app/modules/assessment/services/question_bank_service.py';submit=extract_function(path,'submit_for_review',scope);approve=extract_function(path,'approve',scope);reject=extract_function(path,'reject',scope)
  with self.assertRaises(ValueError):asyncio.run(submit(cls,db,item_id=7))
  self.assertEqual(value.status,Status.DRAFT);self.assertEqual(db.rollbacks,1)
  db.variant=variant_for(value);asyncio.run(submit(cls,db,item_id=7));self.assertEqual(value.status,Status.REVIEW)
  result=asyncio.run(approve(cls,db,item_id=7,reviewer_user_id=9));self.assertEqual(value.status,Status.READY);self.assertEqual(result.item_status,Status.READY);self.assertEqual(len(reviews),1)
  value.status=Status.REVIEW;db.variant.payload['answer_key']['value']='B'
  with self.assertRaises(ValueError):asyncio.run(approve(cls,db,item_id=7,reviewer_user_id=9))
  self.assertEqual(value.status,Status.REVIEW)
  asyncio.run(reject(cls,db,item_id=7,reviewer_user_id=9));self.assertEqual(value.status,Status.REJECTED);self.assertEqual(len(reviews),2)
 def test_stale_translation_and_legacy(self):
  value=item();db=DB(variant_for(value));value.text+=' Changed'
  with self.assertRaises(ValueError):asyncio.run(service.require_bilingual_ready(db,value,Status.DRAFT))
  value.requires_bilingual=False;asyncio.run(service.require_bilingual_ready(DB(),value,Status.DRAFT))
  value.requires_bilingual=True;db=DB(variant_for(value));db.refresh_action=lambda v:setattr(v,'status',Status.READY)
  with self.assertRaises(ValueError):asyncio.run(service.require_bilingual_ready(db,value,Status.DRAFT))
 def test_existing_renderers_and_translated_panels_all_types(self):
  if 'pytest' not in sys.modules:
   fake=types.ModuleType('pytest');fake.mark=NS(parametrize=lambda *a,**kw:lambda fn:fn);sys.modules['pytest']=fake
  import test_question_bank_i18n as legacy
  for kind in Type:
   for language in ['ru','kk']:legacy.test_editor_detail_review_for_all_types(language,kind.value)
   original=legacy.question(kind.value);payload=source_payload(original);translated=make_variant(payload,kind,translations(payload,kind));assert_variant_contract(payload,translated,kind)
   view=NS(**vars(original));view.__dict__.update(translated);view.language=Lang.KAZAKH
   for ui in ['ru','kk']:
    html=environment().get_template('teacher/assessment/question_bank/components/language_version.html').render(request=request(ui),bilingual_item=view)
    self.assertIn('Қазақша',html);self.assertIn('Аударма',html)
  original=source_payload(item());original['text']='Вычислите 2+2 и $x+3$'
  values=translations(original,Type.SINGLE_CHOICE)
  text_index=next(i for i,(path,_) in enumerate(translation_fields(original,Type.SINGLE_CHOICE)) if path==('text',))
  values[f'f{text_index}']='Есептеңіз 2+3 және $x+3$'
  with self.assertRaises(ValueError):make_variant(original,Type.SINGLE_CHOICE,values)
 def test_model_and_migration_contract(self):
  self.assertTrue(QuestionBankItem.__table__.c.requires_bilingual.default.arg);self.assertEqual(str(QuestionBankItem.__table__.c.requires_bilingual.server_default.arg),'false')
  table=QuestionBankLanguageVariant.__table__;self.assertEqual([c.name for c in table.primary_key],['item_id','language']);self.assertEqual(next(iter(table.c.item_id.foreign_keys)).ondelete,'CASCADE')
  path=PROJECT/'app/db/migrations/versions/e26b104ac601_question_bank_language_variants.py';scope={};exec(compile(path.read_text(),str(path),'exec'),scope);self.assertEqual(scope['down_revision'],'d94f103ac527')
 def test_workspace_and_expert_panel_in_both_locales(self):
  source=item();target=variant_for(source);path='app/modules/assessment/services/bilingual_question_views.py';tree=ast.parse((PROJECT/path).read_text());fn=copy.deepcopy(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='localized_view'))
  import dataclasses
  scope=dict(fields=dataclasses.fields,is_dataclass=dataclasses.is_dataclass,SimpleNamespace=NS,AssessmentLanguage=Lang);exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),path,'exec'),scope)
  original=scope['localized_view'](source,source_payload(source),'ru');translated=scope['localized_view'](source,target.payload,'kk')
  rows=[dict(name=f'f{i}',source=text,value=target.payload.get('text',''),number=i+1) for i,(_,text) in enumerate(translation_fields(source_payload(source),source.question_type))]
  for lang in ['ru','kk']:
   html=environment().get_template('teacher/assessment/question_bank/languages.html').render(request=request(lang),user={'role':'teacher','full_name':'DATA USER'},item=source,source_view=original,target_view=translated,target_language='kk',rows=rows,source_hash=fingerprint(source),stale=False,saved=True,readonly=False,error=None)
   self.assertIn('name="source_hash"',html);self.assertIn('Русский',html);self.assertIn('Қазақша',html);self.assertIn('Аударма',html);self.assertNotIn('source_fingerprint',html)
 def test_ai_provider_exact_field_map_and_failures(self):
  path=PROJECT/'app/modules/assessment/ai/question_translation_provider.py';tree=ast.parse(path.read_text());node=next(n for n in tree.body if isinstance(n,ast.ClassDef));calls=[];response=NS(status='completed',output_text=json.dumps({'f0':'Аударма'}))
  async def create(**kw):calls.append(kw);return response
  client=NS(responses=NS(create=create))
  class Provider:
   def __init__(self,**kwargs):pass
   def _require_api_key(self):return 'test'
   def _require_model(self):return 'mock-model'
   def _get_client(self,**kwargs):return client
  scope=dict(json=json,OpenAIQuestionProvider=Provider);exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(path),'exec'),scope);provider=scope['QuestionTranslationProvider']()
  result=asyncio.run(provider.translate([(('text',),'Исходный текст')],'kk'));self.assertEqual(result,{'f0':'Аударма'});self.assertFalse(calls[0]['store']);self.assertEqual(calls[0]['text']['format']['type'],'json_object');self.assertIn('JSON',calls[0]['input'])
  for output in ['{}','[]','{"f0":"ok","extra":"hack"}','{"f0":2}']:
   response.output_text=output
   with self.assertRaises(ValueError):asyncio.run(provider.translate([(('text',),'Source')],'kk'))
if __name__=='__main__':unittest.main()
