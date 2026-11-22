"""Offline tests for report lists and assignment UI; no DB, uploads or real requests."""
import asyncio,json,re,subprocess,unittest
from datetime import date
from types import SimpleNamespace as NS
from html.parser import HTMLParser
from test_ui_language import environment,request,PROJECT
from app.core.i18n import translate
from app.core.planning_period import MONTH_NAMES_KZ
from app.core.reports_i18n import reports_http_exception_handler,reports_message
from app.modules.planning.enums import PlanItemStatus
from app.modules.reports.enums import TaskDocumentStatus,DocumentType,TaskDocumentSource
from app.modules.reports.schemas.report_assignment_dto import ReportAssignmentPageDTO,ReportAssignmentExecutorDTO,ReportAssignmentRowDTO
from app.modules.reports.schemas.task_reports_dto import TaskReportsPageDTO,TaskReportListItemDTO,ExecutionFinalDocumentDTO
PAGES=['staff/reports/report_assignments.html','staff/reports/staff_my_reports.html','staff/reports/template_reports.html','staff/reports/user_templates/template_list.html','staff/reports/user_templates/template_select.html']
class Fields(HTMLParser):
 def __init__(self):super().__init__();self.fields=[]
 def handle_starttag(self,tag,attrs):
  if tag in ['input','form','select','option','textarea','button']:
   self.fields.append((tag,tuple((k,v) for k,v in attrs if k not in ['title','placeholder','aria-label','class','aria-pressed','data-confirm'])))

def context(lang,page,filled=True,state='pending'):
 row=ReportAssignmentRowDTO(selected_report_id=21,report_type_id=2,report_code='lesson_observation',report_name='Сабақты бақылау парағы',target_kind='teacher',target_value='14',target_label='DATA TEACHER',assigned_staff_member_id=3,assigned_staff_full_name='DATA EXECUTOR',assignment_status=state,waived_reason='DATA REASON' if state=='waived' else None)
 executor=ReportAssignmentExecutorDTO(staff_member_id=3,full_name='DATA EXECUTOR',assignment_kind='primary',assignment_kind_label='Негізгі орындаушы',is_primary=True)
 assignments=ReportAssignmentPageDTO(month_item_id=9,month=10,task_topic='DATA <b>TOPIC</b>',task_goal='DATA GOAL',period_text='DATA PERIOD',reports=[row] if filled else [],executors=[executor])
 doc=ExecutionFinalDocumentDTO(id=5,status=TaskDocumentStatus.SUBMITTED,document_type=DocumentType.REFERENCE,original_file_name='DATA ORIGINAL NAME.pdf',file_path='DATA FILE',is_final=True)
 report=TaskReportListItemDTO(selected_report_id=21,report_type_id=2,report_code='lesson_observation',report_label='Сабақты бақылау парағы',target_kind='teacher',target_label='DATA TEACHER',target_value='14',assigned_staff_member_id=3,is_filled=state=='completed',is_completed=state=='completed',has_draft=state=='pending',document_status=TaskDocumentStatus.DRAFT,source=TaskDocumentSource.TEMPLATE,has_system_template=True,has_user_template=True,can_fill_system_report=state=='pending',can_view_system_report=state=='completed',system_fill_route='system_fill',system_pdf_view_route='system_view',system_report_id=11,can_fill_user_report=True,user_fill_route='user_fill',user_pdf_view_route='user_view')
 data=TaskReportsPageDTO(month_item_id=9,task_topic='DATA <b>TOPIC</b>',task_title='DATA TASK',reports=[report] if filled else [],is_primary_executor=filled,can_manage_report_assignments=filled,all_reports_resolved=state!='pending',pending_reports_count=int(state=='pending'),waived_reports_count=int(state=='waived'))
 task=NS(month_item_id=9,topic='DATA <b>TOPIC</b>',period_text='DATA PERIOD',task_status='in_progress',task_status_label='Орындалу үстінде',assigned_reports_count=1)
 template=NS(id=8,title='DATA <b>TEMPLATE</b>',description='DATA DESCRIPTION',report_label='Сабақты бақылау парағы',report_code='lesson_observation',content_text='DATA CONTENT')
 return dict(request=request(lang),user={'role':'school_staff','full_name':'DATA USER'},page_data=assignments if page.endswith('report_assignments.html') else data,month=10,MONTH_NAMES=MONTH_NAMES_KZ,tasks=[task] if filled else [],task='DATA TASK' if filled else None,task_topic='DATA <b>TOPIC</b>',task_month=10,reports=[report] if filled else [],month_item_id=9,selected_report_id=21,report_code='lesson_observation',report_label='Сабақты бақылау парағы',target_label='DATA TEACHER',target_kind='teacher',templates_list=[template] if filled else [],error=None,warning=None,success=None,task_status=PlanItemStatus.DONE if state=='completed' else PlanItemStatus.IN_PROGRESS,is_done=state=='completed',final_locked=state=='completed',completion_mode='final_with_system_reports',is_simple_final_document=False,is_final_with_system_reports=True,all_reports_completed=state=='completed',all_reports_signed=state=='completed',required_reports_count=1,completed_reports_count=int(state=='completed'),signed_reports_count=int(state=='completed'),final_documents=[doc] if filled else [],current_final_document=doc if filled and state=='completed' else None,has_final_document=filled,final_document_status=doc.status,review_reports_text='DATA REVIEW REPORT',review_place_text='DATA REVIEW PLACE')

class ReportsI18nTests(unittest.TestCase):
 def test_pages_preserve_forms_and_user_data(self):
  for page in PAGES:
   for state in ['pending','completed','waived']:
    for filled in [False,True]:
     with self.subTest(page=page,state=state,filled=filled):
      texts=[environment().get_template(page).render(**context(lang,page,filled,state)) for lang in ['ru','kk']]
      parsed=[]
      for text in texts:
       self.assertNotIn('DATA <b>TOPIC</b>',text);self.assertNotIn('DATA <b>TEMPLATE</b>',text);p=Fields();p.feed(text);parsed.append(p.fields)
      self.assertEqual(parsed[0],parsed[1])
      if filled and 'user_templates' in page:
       for text in texts:self.assertIn('DATA &lt;b&gt;TEMPLATE&lt;/b&gt;',text);self.assertIn('DATA DESCRIPTION',text)
      if filled and page.endswith('report_assignments.html'):
       self.assertIn('Лист наблюдения урока',texts[0]);self.assertIn('Сабақты бақылау парағы',texts[1]);self.assertIn('DATA TEACHER',texts[1])
      if filled and page.endswith('template_reports.html'):
       self.assertIn('DATA ORIGINAL NAME.pdf',texts[0]);self.assertIn('DATA ORIGINAL NAME.pdf',texts[1]);self.assertIn('Отправлен на рассмотрение',texts[0]);self.assertIn('Қарауға жіберілді',texts[1])

 def test_feedback_and_error_scope(self):
  from starlette.exceptions import HTTPException
  for lang in ['ru','kk']:
   req=request(lang);req.scope['path']='/staff/reports/templates/my'
   message='Распределение отчётов сохранено. Создано: 2, изменено: 3, без изменений: 4.'
   result=reports_message(req,message)
   self.assertTrue(all(n in result for n in ['2','3','4']))
   self.assertIn('өзгертілді' if lang=='kk' else 'изменено',result)
   self.assertEqual(reports_message(req,'Шаблон создан'),translate('Шаблон создан',lang))
   response=asyncio.run(reports_http_exception_handler(req,HTTPException(403,'Выбранный сотрудник не является исполнителем этой задачи.',headers={'X-Test':'kept'})))
   self.assertEqual(response.status_code,403);self.assertEqual(response.headers['X-Test'],'kept');self.assertEqual(json.loads(response.body)['detail'],translate('Выбранный сотрудник не является исполнителем этой задачи.',lang))
   req.scope['path']='/unrelated';response=asyncio.run(reports_http_exception_handler(req,HTTPException(418,'UNCHANGED')));self.assertEqual(json.loads(response.body)['detail'],'UNCHANGED')

 def test_template_query_feedback(self):
  from urllib.parse import urlencode
  for lang in ['ru','kk']:
   page='staff/reports/user_templates/template_list.html';data=context(lang,page)
   data['request'].scope['query_string']=urlencode({'success':'Шаблон создан'}).encode()
   text=environment().get_template(page).render(**data)
   self.assertIn(translate('Шаблон создан',lang),text)

 def test_reassignment_and_waiver_js(self):
  for lang in ['ru','kk']:
   text=environment().get_template(PAGES[0]).render(**context(lang,PAGES[0]))
   script=next(s for s in re.findall(r'<script\b[^>]*>(.*?)</script>',text,re.S) if 'submitActionForm' in s)
   messages=environment().from_string('{{ ui_messages()|tojson }}').render(request=request(lang))
   source='const messages='+messages+''';const vm=require('vm');
let allow=false,reason=null;const posts=[],alerts=[];
const select={value:'3',disabled:false,classList:{add(){},remove(){}},addEventListener(){},focus(){},scrollIntoView(){}};
const mainForm={addEventListener(e,f){this.submitEvent=f}};
const button=()=>({dataset:{reportId:'21',monthItemId:'9',month:'10'},addEventListener(e,f){this.click=f}});
const reassign=button(),waive=button();
const doc={addEventListener(e,f){f()},getElementById(){return mainForm},querySelector(){return select},querySelectorAll(q){return q==='.assignment-select'?[select]:q.includes('reassign')?[reassign]:q.includes('waive')?[waive]:[]},createElement(tag){return tag==='form'?{style:{},children:[],appendChild(i){this.children.push(i)},submit(){posts.push({action:this.action,fields:Object.fromEntries(this.children.map(i=>[i.name,i.value]))})}}:{}},body:{appendChild(){}}};
const sandbox={document:doc,alert(t){alerts.push(t)},confirm(){return allow},prompt(){return reason},window:{SchoolMonitorI18n:{t(k){return messages[k]??k}}}};
vm.runInNewContext(SCRIPT,sandbox);
reassign.click();if(posts.length)throw Error('cancel reassign');allow=true;reassign.click();
reason=null;waive.click();if(posts.length!==1)throw Error('cancel reason');
reason=' ';waive.click();if(posts.length!==1)throw Error('empty reason');
reason='x'.repeat(2001);waive.click();if(posts.length!==1)throw Error('long reason');
reason='  DATA {reason} "quoted"  ';waive.click();
process.stdout.write(JSON.stringify({posts,alerts}));
'''.replace('SCRIPT',json.dumps(script))
   result=subprocess.run(['node','-e',source],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr);data=json.loads(result.stdout)
   self.assertEqual(data['posts'],[{'action':'/staff/tasks/9/report-assignments/21/reassign','fields':{'month':'10','staff_member_id':'3'}},{'action':'/staff/tasks/9/report-assignments/21/waive','fields':{'month':'10','reason':'DATA {reason} "quoted"'}}])
   self.assertIn(translate('Причина обязательна.',lang),data['alerts']);self.assertIn(translate('Причина слишком длинная. Максимум 2000 символов.',lang),data['alerts'])
if __name__=='__main__':unittest.main()
