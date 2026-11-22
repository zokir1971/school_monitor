"""Execution UI offline validation; no real task acceptance, upload, or DB writes."""
import asyncio,json,re,subprocess,unittest
from datetime import date
from html.parser import HTMLParser
from types import SimpleNamespace as NS
from test_ui_language import environment,request,PROJECT
from app.core.i18n import translate
from app.core.planning_period import MONTH_NAMES_KZ
from app.core.execution_i18n import execution_http_exception_handler

class Fields(HTMLParser):
 def __init__(self):super().__init__();self.fields=[];self.data={}
 def handle_starttag(self,tag,attrs):
  data=dict(attrs)
  if data.get('id')=='task-execution-json-data':self.data=data
  if data.get('id')=='task_status_view':return
  if tag in ['form','input','select','textarea','button','option']:
   self.fields.append((tag,tuple((k,v) for k,v in attrs if k not in ['title','placeholder','aria-label','class','aria-pressed'])))

def context(lang,state='in_progress',filled=True):
 task=NS(month_item_id=9,topic='DATA <b>TOPIC</b>',goal='DATA GOAL',control_object='DATA OBJECT',control_type='DATA TYPE',control_form='DATA FORM',review_place='DATA REVIEW',period_text='DATA PERIOD',planned_start=date(2026,10,5),planned_end=date(2026,10,11),week_of_month=2,status=state,status_label={'todo':'Жоспарланған','in_progress':'Орындалу үстінде','done':'Орындалды','reviewed':'Қаралды','not_executed':'Орындалмады'}[state],action_kind='take' if state=='todo' else 'open',action_url='/staff/tasks/execute?task_id=9',action_label=None,action_css=None,primary_assignee_name='DATA PRIMARY',can_fill_reports=True,has_report_assignments=filled)
 execution=NS(control_scope='teacher',control_form='personal',control_kind='thematic',report_types=['lesson_observation'],subjects=['math'],class_groups=[],parallel_classes=[],teacher_ids=['14'],teacher_id=None,completion_mode='final_with_system_reports',report_type=None)
 flow={'scopes':[{'code':'teacher','label':'Мұғалім'}],'forms_by_scope':{'teacher':[{'code':'personal','label':'Жеке бақылау'}]},'kinds':[{'code':'thematic','label':'Тақырыптық бақылау'}],'details_by_scope':{},'teachers_by_subject':{'math':[{'code':'14','label':"DATA O'CONNOR"}]}}
 state_json=json.dumps({'control_scope':'teacher','teacher_name':"DATA O'CONNOR",'report_types':['lesson_observation']})
 return dict(request=request(lang),user={'role':'school_staff','full_name':'DATA USER'},month=10,MONTH_NAMES=MONTH_NAMES_KZ,current_week=2,primary_tasks=[task] if filled else [],co_executor_tasks=[task] if filled else [],tasks=[task] if filled else [],selected_task_id=9,selected_task=task,execution=execution if filled else None,control_flow=flow if filled else {},state_json=state_json,current_draft=None,report_types=[],can_submit=True,error=None)

class ExecutionI18nTests(unittest.TestCase):
 def test_pages_preserve_form_contract(self):
  for page in ['staff/tasks/school_staff_task.html','staff/tasks/task_execute.html','staff/partials/task_execute_details.html']:
   for state in ['todo','in_progress','done','reviewed','not_executed']:
    for filled in [False,True]:
     with self.subTest(page=page,state=state,filled=filled):
      texts=[environment().get_template(page).render(**context(lang,state,filled)) for lang in ['ru','kk']]
      parsers=[]
      for text in texts:
       self.assertNotIn('DATA <b>TOPIC</b>',text);parser=Fields();parser.feed(text);parsers.append(parser)
      self.assertEqual(parsers[0].fields,parsers[1].fields)
      if page.endswith('school_staff_task.html'):
       self.assertIn('Октябрь',texts[0]);self.assertIn('Қазан',texts[1])
      if page.endswith('task_execute_details.html'):
       for parser in parsers:
        self.assertEqual(json.loads(parser.data['data-state']),json.loads(context('ru')['state_json']))
        self.assertEqual(json.loads(parser.data['data-control-flow']),context('ru',filled=filled)['control_flow'])
       self.assertIn('DATA GOAL',texts[0]);self.assertIn('DATA GOAL',texts[1])

 def test_completion_flow_toggle(self):
  for lang in ['ru','kk']:
   text=environment().get_template('staff/partials/task_execute_details.html').render(**context(lang))
   script=next(s for s in re.findall(r'<script\b[^>]*>(.*?)</script>',text,re.S) if 'initializeTaskCompletionFlow' in s)
   source='''const vm=require('vm');const simple={hidden:true},reports={hidden:true};
const modes=['simple_final_document','final_with_system_reports'].map(value=>({value,addEventListener(e,f){this.change=f}}));
const root={querySelector(q){return q==='#simple-final-document-actions'?simple:q==='#system-reports-execution-flow'?reports:null},querySelectorAll(){return modes}};
vm.runInNewContext(SCRIPT,{document:{getElementById(){return root}}});
if(!simple.hidden||!reports.hidden)throw Error('empty mode');modes[0].change();if(simple.hidden||!reports.hidden)throw Error('simple');modes[1].change();if(!simple.hidden||reports.hidden)throw Error('reports');
'''.replace('SCRIPT',json.dumps(script))
   result=subprocess.run(['node','-e',source],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr)

 def test_generated_payload_is_canonical_in_both_locales(self):
  script=(PROJECT/'app/web/static/js/task_execute.js').read_text()
  script=script.replace('  window.initTaskExecuteForm = initTaskExecuteForm;','  window.__test = {buildGeneratedMaterials, renderGeneratedMaterials, executionLabel};\n  window.initTaskExecuteForm = initTaskExecuteForm;')
  payloads=[]
  for lang in ['ru','kk']:
   messages=environment().from_string('{{ ui_messages()|tojson }}').render(request=request(lang))
   source='const messages='+messages+''';const vm=require('vm');
const summary={},list={},hidden={};
const reports=[{value:'analytical_reference',checked:true,dataset:{label:'Анықтама'}},{value:'lesson_observation',checked:true,dataset:{label:'Сабақты бақылау парағы'}}];
const teachers=[{value:'14',checked:true,dataset:{label:'DATA TEACHER'}}];
const root={querySelector(q){return q==='#control_scope'?{value:'teacher'}:q==='#materials-preview-summary'?summary:q==='#materials-preview-list'?list:q==='#generated_reports_json'?hidden:null},querySelectorAll(q){return q.includes('report_types')?reports:q.includes('teacher_ids')?teachers:[]}};
const document={addEventListener(){},body:{addEventListener(){}}};
const sandbox={document,window:{SchoolMonitorI18n:{t(k,values={}){const text=messages[k]??k;return text.replace(/\\{(p\\d+)\\}/g,(m,n)=>n in values?String(values[n]):m)}}}};
vm.createContext(sandbox);vm.runInContext(SCRIPT,sandbox);
const generated=sandbox.window.__test.buildGeneratedMaterials(root,{});
sandbox.window.__test.renderGeneratedMaterials(root,generated);
process.stdout.write(JSON.stringify({payload:JSON.parse(hidden.value),summary:summary.textContent,list:list.innerHTML,teacher:sandbox.window.__test.executionLabel('DATA TEACHER')}));
'''.replace('SCRIPT',json.dumps(script))
   result=subprocess.run(['node','-e',source],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr);data=json.loads(result.stdout);payloads.append(data['payload'])
   self.assertEqual(data['teacher'],'DATA TEACHER');self.assertEqual(data['payload'][1]['teacher_id'],'14')
   self.assertEqual(data['payload'][1]['report_label'],'Сабақты бақылау парағы');self.assertIn('DATA TEACHER',data['list'])
   self.assertIn('Лист наблюдения урока' if lang=='ru' else 'Сабақты бақылау парағы',data['summary'])
  self.assertEqual(payloads[0],payloads[1])

 def test_errors_are_localized_and_scoped(self):
  from starlette.exceptions import HTTPException
  for lang in ['ru','kk']:
   req=request(lang);req.scope['path']='/staff/tasks/execute'
   response=asyncio.run(execution_http_exception_handler(req,HTTPException(403,'Задача не найдена или недоступна.',headers={'X-Test':'kept'})))
   self.assertEqual(response.status_code,403);self.assertEqual(response.headers['X-Test'],'kept');self.assertEqual(json.loads(response.body)['detail'],translate('Задача не найдена или недоступна.',lang))
   req.scope['path']='/unrelated';response=asyncio.run(execution_http_exception_handler(req,HTTPException(418,'UNCHANGED')))
   self.assertEqual(response.status_code,418);self.assertEqual(json.loads(response.body)['detail'],'UNCHANGED')
if __name__=='__main__':unittest.main()
