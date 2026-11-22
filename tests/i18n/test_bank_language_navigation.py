"""Regression: language switch after an invalid bank POST must return to a GET page."""
import asyncio,unittest
from types import SimpleNamespace as NS
from starlette.requests import Request
from test_ui_language import environment,request
from test_bilingual_questions import extract_function
class BankLanguageNavigationTests(unittest.TestCase):
 def test_switch_targets_workspace_for_both_commands(self):
  env=environment();template=env.from_string('{{ language_return_url() }}')
  for lang in ['ru','kk']:
   for tail in ['add','remove/9','add/']:
    req=request(lang);req.scope['path']='/teacher/assessment/from-bank/212/'+tail
    self.assertEqual(template.render(request=req),'/teacher/assessment/from-bank/212')
   req=request(lang);req.scope['path']='/teacher/assessment/from-bank/212';req.scope['query_string']=b'bank_error=test&after=50'
   self.assertEqual(template.render(request=req),'/teacher/assessment/from-bank/212?bank_error=test&amp;after=50')
 def test_get_recovery_has_no_mutations(self):
  from starlette.responses import RedirectResponse
  scope=dict(RedirectResponse=RedirectResponse)
  fn=extract_function('app/routers/web/assessment/assessment_bank_web.py','command_return',scope)
  result=asyncio.run(fn(NS(url_for=lambda *a,**kw:'/teacher/assessment/from-bank/212'),212))
  self.assertEqual(result.status_code,303);self.assertEqual(result.headers['location'],'/teacher/assessment/from-bank/212')
 def test_redirect_notice_is_localized_and_escaped(self):
  env=environment();tpl=env.from_string('{{ bank_feedback(error) }}')
  for lang,expected in [('ru','Выберите от 1 до 50 заданий.'),('kk','1-ден 50-ге дейін тапсырма таңдаңыз.')]:
   self.assertEqual(tpl.render(request=request(lang),error='Выберите от 1 до 50 заданий.'),expected)
   self.assertNotIn('<script>',tpl.render(request=request(lang),error='<script>unsafe</script>'))
 def test_actual_get_routes_redirect_without_db_commands(self):
  import ast,logging,httpx
  from fastapi import APIRouter,Depends,FastAPI,Request
  from starlette.responses import RedirectResponse
  from test_ui_language import PROJECT
  async def dependency():return NS(id=3)
  tree=ast.parse((PROJECT/'app/routers/web/assessment/assessment_bank_web.py').read_text())
  tree.body=[node for node in tree.body if not isinstance(node,(ast.Import,ast.ImportFrom))]
  scope=dict(APIRouter=APIRouter,Depends=Depends,Request=Request,RedirectResponse=RedirectResponse,logging=logging,get_db=dependency,require_teacher_workspace=dependency)
  exec(compile(tree,'assessment_bank_web.py','exec'),scope)
  app=FastAPI();app.include_router(scope['router'])
  async def check():
   async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
    for suffix in ['add','remove/9']:
     response=await client.get('/teacher/assessment/from-bank/212/'+suffix)
     self.assertEqual(response.status_code,303);self.assertEqual(response.headers['location'],'http://test/teacher/assessment/from-bank/212')
  asyncio.run(check())
