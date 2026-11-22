"""Offline language/snapshot/transaction-boundary checks."""
import asyncio,copy,unittest
from types import SimpleNamespace as NS
from decimal import Decimal
from unittest.mock import patch
from test_ui_language import environment,request,PROJECT
from test_bilingual_questions import item,variant_for,Status,Type
from app.modules.assessment.services import assessment_bank_service as bank

class DB:
 def __init__(self):self.added=[];self.deleted=[];self.flushes=0;self.statements=[];self.assessment=None
 def add(self,v):self.added.append(v)
 def add_all(self,v):self.added.extend(v)
 async def delete(self,v):self.deleted.append(v)
 async def flush(self):self.flushes+=1
 async def execute(self,s):self.statements.append(str(s.whereclause)+(' FOR UPDATE' if s._for_update_arg is not None else ''));return NS(scalar_one_or_none=lambda:self.assessment,scalars=lambda:NS(all=lambda:[]))
def target(language='kk',status='draft'):
 return NS(id=20,school_id=4,created_by_user_id=3,title='Работа <unsafe>',subject_id=2,max_score=None,status=status,input_mode='online',settings=dict(bank_builder_version=1,bank_language=language,bank_grade=5))
def run(coro):return asyncio.run(coro)
ARGS=dict(assessment_id=20,school_id=4,user_id=3,staff_member_id=5)
class AssessmentBankTests(unittest.TestCase):
 def test_exact_language_ready_only_and_no_fallback(self):
  for src,dst in [('ru','kk'),('kk','ru')]:
   original=item();original.language=src;original.status=Status.READY;v=variant_for(original);variants={(7,dst):v}
   self.assertEqual(bank.choose_payload(original,dst,variants)['text'],v.payload['text'])
   self.assertEqual(bank.choose_payload(original,src,variants)['text'],original.text)
   for bad in [{},{(7,dst):NS(payload=v.payload,source_fingerprint='stale')}]:
    for lang in [src,dst]:
     with self.assertRaises(bank.BankSelectionError):bank.choose_payload(original,lang,bad)
   original.status=Status.REVIEW
   with self.assertRaises(bank.BankSelectionError):bank.choose_payload(original,dst,variants)
  original=item();original.status=Status.READY;original.requires_bilingual=False
  self.assertEqual(bank.choose_payload(original,'ru',{})['text'],original.text)
  for lang in ['kk','en','']:
   with self.assertRaises(bank.BankSelectionError):bank.choose_payload(original,lang,{})
 def test_tampered_and_stale_translation(self):
  original=item();original.status=Status.READY;v=variant_for(original);v.payload['answer_key']['value']='B'
  with self.assertRaises(bank.BankSelectionError):bank.choose_payload(original,'kk',{(7,'kk'):v})
  v=variant_for(original);original.text+=' changed'
  with self.assertRaises(bank.BankSelectionError):bank.choose_payload(original,'kk',{(7,'kk'):v})
 def test_snapshot_all_types_independent_answers_teacher_only(self):
  for kind in Type:
   original=item(kind);payload=bank.source_payload(original);values=bank.snapshot_values(original,payload,'kk',20,1);q=NS(id=11,**values);view=bank.question_view(q,'kk')
   self.assertEqual(view.language.value,'kk');self.assertEqual(view.text_segments,payload['text_segments']);self.assertEqual(view.answer_key,payload['answer_key']);self.assertEqual(view.explanation,payload['explanation'])
   self.assertNotIn('_bank_explanation',q.content);self.assertNotIn('answer_key',q.content['_bank_source']);self.assertEqual(q.content['_bank_source']['objective_ids'],[8])
   values['answer_key']['value']='changed';values['content']['options'].clear();values['content']['_statement_segments'].clear()
   self.assertEqual(original.answer_key['value'],'A');self.assertEqual(len(original.content['options']),2);self.assertEqual(len(original.text_segments),2)
 def test_add_locks_duplicate_and_atomic_failure(self):
  original=item();original.status=Status.READY;v=variant_for(original);a=target();db=DB()
  async def own(*args,**kw):self.assertTrue(kw['lock']);return a
  async def saved(*args):return []
  async def load(*args,**kw):return [original]
  async def variants(*args):return {(7,'kk'):v}
  with patch.multiple(bank,own_assessment=own,saved_questions=saved,load_items=load,load_variants=variants,AssessmentQuestion=lambda **kw:NS(id=10,**kw)):
   run(bank.add_from_bank(db,**ARGS,item_ids=[7]));self.assertEqual(len(db.added),1);self.assertEqual(a.max_score,Decimal(1));self.assertIn('FOR UPDATE',db.statements[0]);self.assertEqual(db.added[0].text,v.payload['text'])
   async def duplicate(*args):return db.added
   with patch.object(bank,'saved_questions',duplicate):
    with self.assertRaises(bank.BankSelectionError):run(bank.add_from_bank(db,**ARGS,item_ids=[7]))
   with self.assertRaises(bank.BankSelectionError):run(bank.add_from_bank(db,**ARGS,item_ids=[7,99]))
   second=copy.deepcopy(original);second.id=8
   async def partial(*args,**kw):return [original,second]
   with patch.object(bank,'load_items',partial):
    with self.assertRaises(bank.BankSelectionError):run(bank.add_from_bank(db,**ARGS,item_ids=[7,8]))
   self.assertEqual(len(db.added),1)
 def test_delete_scoped_and_frozen_status(self):
  a=target();db=DB();qs=[NS(id=1,max_score=Decimal(2),is_active=True),NS(id=2,max_score=Decimal(3),is_active=True)]
  async def own(*args,**kw):return a
  async def saved(*args):return qs
  with patch.multiple(bank,own_assessment=own,saved_questions=saved):
   run(bank.remove_question(db,**ARGS,question_id=1));self.assertEqual(a.max_score,3)
   with self.assertRaises(bank.BankSelectionError):run(bank.remove_question(db,**ARGS,question_id=99))
   for state in ['ready','active','completed']:
    a.status=state
    with self.assertRaises(bank.BankSelectionError):run(bank.remove_question(db,**ARGS,question_id=2))
  self.assertEqual(len(db.deleted),1)
 def test_scope_owner_and_creation_contract(self):
  db=DB()
  async def denied(*args,**kw):return False
  with patch.object(bank.TeacherQuestionBankRepo,'has_teaching_scope',denied):
   with self.assertRaises(bank.BankSelectionError):run(bank.ensure_scope(db,5,2,5))
  with self.assertRaises(bank.BankSelectionError):run(bank.own_assessment(db,20,4,3,5,lock=True))
  self.assertIn('school_id',db.statements[-1]);self.assertIn('created_by_user_id',db.statements[-1]);self.assertIn('FOR UPDATE',db.statements[-1])
  async def allowed(*args):pass
  args=dict(school_id=4,user_id=3,staff_member_id=5,subject_id=2,grade_level=5,title=' Test ')
  with patch.object(bank,'ensure_scope',allowed),patch.object(bank,'Assessment',lambda **kw:NS(id=20,**kw)):
   self.assertEqual(run(bank.create_draft(db,**args,language='kk')),20);self.assertEqual(db.added[0].settings['bank_language'],'kk');self.assertEqual(db.added[0].title,'Test')
   with self.assertRaises(bank.BankSelectionError):run(bank.create_draft(db,**args,language=''))
 def test_both_interfaces_do_not_change_task_language(self):
  env=environment();user=NS(full_name='Teacher',role='teacher',ui_language=None);scope=NS(subject_id=2,grade_level=5,subject_name_kz='Математика KZ',subject_name_ru='Математика RU')
  original=item();original.status=Status.READY;v=variant_for(original);q=NS(id=11,**bank.snapshot_values(original,v.payload,'kk',20,1));view=bank.question_view(q,'kk')
  for ui in ['ru','kk']:
   req=request(ui);text=env.get_template('teacher/assessment/from_bank/index.html').render(request=req,user=user,error=None,values={},teaching_scope=[scope],assessments=[target()])
   for s in ['value="ru"','value="kk"','value=""']:self.assertIn(s,text)
   text=env.get_template('teacher/assessment/from_bank/workspace.html').render(request=req,user=user,assessment=target(),language='kk',grade_level=5,error=None,saved=[dict(question=q,view=view)],rows=[NS(id=7,view=None,error='Нет проверенной версии на выбранном языке.')],used={7},next_after=51,after=0,editable=True)
   self.assertIn(v.payload['text'],text);self.assertNotIn('name="item_ids"',text);self.assertIn('&lt;unsafe&gt;',text);self.assertIn('after=51',text)
 def test_web_command_commit_and_error_rollback(self):
  from test_bilingual_questions import extract_function
  class Form(dict):
   def getlist(self,key):return self[key]
  class Request:
   async def form(self):return Form(item_ids=['7'])
   def url_for(self,*args,**kw):
    from starlette.datastructures import URL
    return URL('http://test/workspace/20')
  class WebDB(DB):
   commits=0;rollbacks=0;refreshes=0
   async def commit(self):self.commits+=1
   async def rollback(self):self.rollbacks+=1
   async def refresh(self,user):self.refreshes+=1
  async def workspace(*args,**kw):return NS(status_code=kw.get('status_code'),error=kw.get('error'))
  async def add_ok(*args,**kw):self.assertEqual(kw['item_ids'],[7])
  from starlette.responses import RedirectResponse
  scope=dict(Depends=lambda x:None,get_db=None,require_teacher_workspace=None,boundary=lambda user:dict(school_id=4,user_id=3,staff_member_id=5),number=int,
   service=NS(BankSelectionError=bank.BankSelectionError,add_from_bank=add_ok),
   RedirectResponse=RedirectResponse,workspace=workspace,logger=NS(info=lambda *a,**kw:None))
  add=extract_function('app/routers/web/assessment/assessment_bank_web.py','add',scope)
  db=WebDB();response=run(add(Request(),20,db,NS(id=3)));self.assertEqual(response.status_code,303);self.assertEqual(db.commits,1)
  async def bad(*args,**kw):raise bank.BankSelectionError('Нет проверенной версии на выбранном языке.')
  scope['service'].add_from_bank=bad
  response=run(add(Request(),20,db,NS(id=3)));self.assertEqual(response.status_code,303);self.assertIn('bank_error=',response.headers['location']);self.assertEqual(db.rollbacks,1);self.assertEqual(db.refreshes,1);self.assertEqual(db.commits,1)
