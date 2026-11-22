"""Language-command navigation and task-language instructions."""
import ast,asyncio,json,logging,unittest
from types import SimpleNamespace as NS
from test_ui_language import PROJECT,environment,request
from app.core.question_instructions import PAIRS
class TranslationNavigationTests(unittest.TestCase):
 def test_instruction_uses_task_language_for_all_types(self):
  env=environment();tpl=env.from_string('{{ question_instruction(value, language) }}')
  for ui in ['ru','kk']:
   for ru,kk in PAIRS:
    self.assertEqual(tpl.render(request=request(ui),value=kk,language='ru'),ru)
    self.assertEqual(tpl.render(request=request(ui),value=ru,language=NS(value='kk')),kk)
 def test_language_return_target_is_get_workspace(self):
  template=environment().from_string('{{ language_return_url() }}')
  for ui in ['ru','kk']:
   for suffix in ['ai','ai/']:
    req=request(ui);req.scope['path']='/teacher/question-bank/items/98/languages/'+suffix
    self.assertEqual(template.render(request=req),'/teacher/question-bank/items/98/languages')
 def test_actual_get_command_has_no_ai_or_mutations(self):
  import httpx
  from fastapi import APIRouter,Depends,Request,HTTPException,FastAPI
  from starlette.responses import RedirectResponse
  async def dependency():return NS(id=3)
  tree=ast.parse((PROJECT/'app/routers/web/assessment/question_bank_languages_web.py').read_text());tree.body=[n for n in tree.body if not isinstance(n,(ast.Import,ast.ImportFrom))]
  scope=dict(APIRouter=APIRouter,Depends=Depends,Request=Request,HTTPException=HTTPException,RedirectResponse=RedirectResponse,get_db=dependency,require_teacher_workspace=dependency)
  exec(compile(tree,'languages.py','exec'),scope);app=FastAPI();app.include_router(scope['router'])
  async def check():
   async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
    result=await client.get('/teacher/question-bank/items/98/languages/ai')
    self.assertEqual(result.status_code,303);self.assertEqual(result.headers['location'],'http://test/teacher/question-bank/items/98/languages')
  asyncio.run(check())
 def test_translation_receives_full_readonly_context(self):
  tree=ast.parse((PROJECT/'app/modules/assessment/ai/question_translation_provider.py').read_text());node=next(n for n in tree.body if isinstance(n,ast.ClassDef));calls=[]
  async def create(**kw):calls.append(kw);return NS(status='completed',output_text='{"f0":"Перевод"}')
  class Provider:
   def __init__(self,**kw):pass
   def _require_api_key(self):return 'test'
   def _require_model(self):return 'test'
   def _get_client(self,**kw):return NS(responses=NS(create=create))
  scope=dict(json=json,OpenAIQuestionProvider=Provider);exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'translation.py','exec'),scope)
  result=asyncio.run(scope['QuestionTranslationProvider']().translate([(('text',),'Текст')],'ru',context={'text':'Whole task context'}))
  self.assertEqual(result,{'f0':'Перевод'});self.assertEqual(len(calls),1);self.assertIn('Whole task context',calls[0]['input']);self.assertIn('natural target-language grammar',calls[0]['instructions'])
