"""Offline unittest checks; no database or messaging calls."""
import asyncio,json,re,subprocess,unittest
from datetime import date,datetime
from types import SimpleNamespace as NS
from html.parser import HTMLParser
from test_ui_language import environment,request,PROJECT
from app.modules.planning.enums import PlanStatus,MonthPlanNotificationStatus
from app.core.planning_i18n import planning_http_exception_handler
from app.core.monthly_i18n import monthly_message_text
from app.core.i18n import translate,catalog

class FormFields(HTMLParser):
 def __init__(self):super().__init__();self.fields=[]
 def handle_starttag(self,tag,attrs):
  if tag in ['form','input','select','option','button','textarea']:self.fields.append((tag,tuple((k,v) for k,v in attrs if k not in ['aria-label','placeholder','title','class','aria-pressed'])))
def context(lang,status='draft',filled=True,can_assign=True):
 def option(role,member,name):return NS(staff_role_id=role,staff_member_id=member,full_name=name,role_label='Кітапханашы',role_context='DATA CONTEXT',position_text='кітапханашы',subject='DATA SUBJECT',selected_as_primary=role==11,selected_as_co_executor=role==12,assignment_kind='primary' if role==11 else 'co_executor')
 primary=option(11,1,'DATA PRIMARY');co=option(12,2,'DATA CO');extra=option(13,3,'DATA EXTRA')
 def group(op):return NS(code='librarian:DATA CONTEXT',label='Кітапханашы',role_context='DATA CONTEXT',options=[op])
 task=NS(id=9,is_included=True,week_of_month=2,period_type='month',period_value_int=10,topic='DATA <b>TOPIC</b>',goal='DATA GOAL',control_object='DATA OBJECT',methods='DATA METHODS',primary_assignee_name='DATA PRIMARY',co_executor_names=['DATA CO'],review_place_labels=['Пед.кеңес'],is_assigned=filled,has_primary_assignee=filled,co_executor_count=1,assignment_label='Назначено (+1)')
 plan=NS(id=5,school_plan_id=7,month=10,year=2026,status=PlanStatus(status))
 recipient=NS(staff_member_id=1,full_name='DATA PRIMARY',is_registered=filled,phone='+77001234567',role_summary='Ответственный и соисполнитель',task_count=2,primary_tasks=[NS(title='DATA TASK',deadline_text='DATA DEADLINE')],co_executor_tasks=[NS(title='DATA CO TASK',deadline_text='DATA CO DEADLINE')])
 return dict(request=request(lang),user={'role':'school_admin','full_name':'DATA USER'},months=[NS(num=10,label='Октябрь')],month=10,school_plan_id=7,active_plan=NS(id=7),month_plan=plan if filled else None,can_build=True,success='Исполнители успешно назначены.',warning=None,info=None,error=None,blocks=[NS(direction_name='DATA DIRECTION',items=[task])] if filled else [],weeks=[NS(week=2,start=date(2026,10,5),end=date(2026,10,11))],notification_progress=NS(sent_total=1,total_recipients=3,sent_count=1,accepted_count=1,pending_count=1),month_item_id=9,row11_id=19,direction_name='DATA DIRECTION',topic='DATA <b>TOPIC</b>',goal='DATA GOAL',week_of_month=2,planned_start=date(2026,10,5),planned_end=date(2026,10,11),is_included=filled,can_assign=can_assign,primary_groups=[group(primary)] if filled else [],planned_co_executor_groups=[group(co)] if filled else [],additional_co_executor_groups=[group(extra)] if filled else [],assigned_participants=[primary,co] if filled else [],selected_primary_staff_role_id=11,selected_co_executor_staff_role_ids=[12],month_plan_id=5,recipients=[recipient] if filled else [],notification_status_map={1:NS(status=MonthPlanNotificationStatus.SENT,opened_at=datetime(2026,10,23,12,30),open_count=2)})

class MonthlyI18nTests(unittest.TestCase):
 def test_pages_and_forms(self):
  for page in ['monthly_tasks','month_item_assignees','month_plan_notifications']:
   for status in ['draft','active','archived']:
    for filled in [False,True]:
     with self.subTest(page=page,status=status,filled=filled):
      texts=[]
      for lang in ['ru','kk']:
       data=context(lang,status,filled)
       if page=='month_plan_notifications' and not filled:data['month_plan']=context(lang,status,True)['month_plan']
       text=environment().get_template('planning/school/'+page+'.html').render(**data)
       self.assertIn(f'<html lang="{lang}">',text);self.assertNotIn('DATA <b>TOPIC</b>',text);texts.append(text)
      fields=[]
      for text in texts:
       parser=FormFields();parser.feed(text);fields.append(parser.fields)
      self.assertEqual(fields[0],fields[1])
      if page=='monthly_tasks':
       self.assertIn('Октябрь',texts[0]);self.assertIn('Қазан',texts[1])
       if filled:
        self.assertIn('DATA GOAL',texts[0]);self.assertIn('DATA GOAL',texts[1]);self.assertIn('Тағайындалды (+1)',texts[1])
        if status!='draft':self.assertRegex(texts[0],r'name="item_9_week" disabled')
      if page=='month_plan_notifications' and filled:
       self.assertIn('DATA DEADLINE',texts[1]);self.assertIn('value="+77001234567"',texts[0]);self.assertIn('Отправлено',texts[0]);self.assertIn('Жіберілді',texts[1])
      if page=='month_item_assignees' and filled:
       self.assertIn('Библиотекарь',texts[0]);self.assertIn('Кітапханашы',texts[1]);self.assertIn('DATA CONTEXT',texts[1]);self.assertIn('библиотекарь',texts[0])

 def test_unavailable_and_feedback(self):
  for lang in ['ru','kk']:
   data=context(lang,filled=False,can_assign=False);data.update(planned_start=None,planned_end=None,week_of_month=None,error='Необходимо выбрать основного исполнителя.')
   text=environment().get_template('planning/school/month_item_assignees.html').render(**data)
   self.assertNotIn('id="assignee-form"',text);self.assertIn(translate('Необходимо выбрать основного исполнителя.',lang),text);self.assertIn(translate('Задача не включена в месячный план.',lang),text)

 def test_single_date_word_order(self):
  for lang in ['ru','kk']:
   for from_start in [True,False]:
    data=context(lang);data['planned_end' if from_start else 'planned_start']=None
    text=environment().get_template('planning/school/month_item_assignees.html').render(**data)
    day='05' if from_start else '11'
    word=('бастап' if from_start else 'дейін') if lang=='kk' else ('с' if from_start else 'до')
    pattern=(day+r'\.10\.2026\s+'+word) if lang=='kk' else (word+r'\s+'+day+r'\.10\.2026')
    self.assertRegex(text,pattern)

 def test_terms_and_current_month(self):
  for lang,unwanted in [('ru','МІБ'),('kk','ВШК')]:
   for key,value in catalog(lang)._catalog.items():
    if isinstance(value,str):self.assertIsNone(re.search(r'\b'+unwanted+r'\b',value),key)
  self.assertIn('ВШК',translate('МІБ жоспары','ru'));self.assertIn('МІБ',translate('ВШК жоспары','kk'))
  for lang in ['ru','kk']:
   row=NS(period_type='months',period_values='9,10',period_value_int=None)
   result=environment().from_string('{{ row|planning_period(10) }}').render(request=request(lang),row=row)
   self.assertEqual(result,'Месяц: Октябрь' if lang=='ru' else 'Ай: Қазан')

 def test_errors(self):
  from starlette.exceptions import HTTPException
  for lang in ['ru','kk']:
   req=request(lang);req.scope['path']='/planning/school/monthly/9/assignees';message='Мұрағатталған айлық жоспардың орындаушыларын өзгертуге болмайды.'
   response=asyncio.run(planning_http_exception_handler(req,HTTPException(403,message,headers={'X-Test':'kept'})))
   self.assertEqual(response.status_code,403);self.assertEqual(response.headers['X-Test'],'kept');self.assertEqual(json.loads(response.body)['detail'],translate(message,lang))
   self.assertEqual(monthly_message_text(req,'Исполнители успешно назначены.'),translate('Исполнители успешно назначены.',lang));self.assertNotIn('PRIVATE DATA',monthly_message_text(req,'PRIVATE DATA'))

 def test_assignee_script(self):
  for lang in ['ru','kk']:
   text=environment().get_template('planning/school/month_item_assignees.html').render(**context(lang))
   script=next(s for s in re.findall(r'<script\b[^>]*>(.*?)</script>',text,re.S) if 'syncPrimaryAndCoExecutors' in s)
   messages=environment().from_string('{{ ui_messages()|tojson }}').render(request=request(lang))
   source='const messages='+messages+''';
const vm=require('vm');
function input(value,member,checked){return {value,checked,disabled:false,dataset:{staffMemberId:member},events:{},addEventListener(e,f){this.events[e]=f},closest(){return {classList:{add(){},remove(){}}}}}}
const primary=input('11','1',true),samePerson=input('14','1',true),co=input('12','2',true);
const button={dataset:{staffRoleId:'12'},events:{},addEventListener(e,f){this.events[e]=f},setAttribute(k,v){this[k]=v}};
const card={classList:{toggle(){}},querySelector(){return button}};
const form={querySelectorAll(q){return q.includes('primary_')?[primary]:[samePerson,co]}};
const doc={getElementById(id){return id==='assignee-form'?form:null},querySelectorAll(q){return q==='.js-remove-coexecutor'?[button]:[]},querySelector(){return card},addEventListener(e,f){f()}};
const sandbox={document:doc,window:{SchoolMonitorI18n:{t(k){return messages[k]}}}};vm.createContext(sandbox);vm.runInContext(SCRIPT,sandbox);
if(!samePerson.disabled||samePerson.checked)throw Error('primary duplicated');
button.events.click();if(co.checked)throw Error('remove');const removed=button.textContent;
button.events.click();if(!co.checked)throw Error('restore');
process.stdout.write(JSON.stringify({removed,restored:button.textContent,primary:primary.value,co:co.value}));
'''.replace('SCRIPT',json.dumps(script))
   result=subprocess.run(['node','-e',source],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr);result=json.loads(result.stdout)
   self.assertEqual(result['removed'],translate('Вернуть',lang));self.assertEqual(result['restored'],translate('Убрать',lang));self.assertEqual((result['primary'],result['co']),('11','12'))
 def test_prepared_notification_is_bilingual_and_preserves_data(self):
  from app.core.monthly_notification_message import build_monthly_notification_message
  recipient=context('ru')['recipients'][0]
  recipient.full_name='DATA {name} <NAME>'
  before=repr(recipient)
  messages=[]
  for lang in ['ru','kk','kz']:
   message=build_monthly_notification_message(recipient=recipient,platform_url='https://school.example/',school_name='DATA SCHOOL',language=lang)
   self.assertIn(recipient.full_name,message)
   for value in ['DATA TASK','DATA CO TASK','DATA DEADLINE','DATA CO DEADLINE','DATA SCHOOL','https://school.example']:
    self.assertIn(value,message)
   self.assertIn('2',message);self.assertEqual(repr(recipient),before);messages.append(message)
  self.assertTrue(messages[0].startswith('Здравствуйте, '));self.assertTrue(messages[1].startswith('Сәлеметсіз бе, '));self.assertEqual(messages[1],messages[2])
  self.assertIn('Отправка выполняется вручную',messages[0]);self.assertIn('қолмен жіберіледі',messages[1])
  self.assertEqual(build_monthly_notification_message(recipient=recipient,platform_url='https://school.example',school_name='DATA SCHOOL'),messages[1])

 def test_service_and_route_wire_language_without_starting_app(self):
  import ast
  module=ast.parse((PROJECT/'app/modules/planning/services/month_plan_notification_service.py').read_text())
  cls=next(node for node in module.body if isinstance(node,ast.ClassDef) and node.name=='MonthPlanNotificationService')
  fn=next(node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name=='build_message');fn.decorator_list=[]
  future=ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)
  sandbox={};exec(compile(ast.fix_missing_locations(ast.Module(body=[future,fn],type_ignores=[])),'<build_message>','exec'),sandbox)
  for lang,heading in [('ru','Здравствуйте'),('kk','Сәлеметсіз бе')]:
   self.assertTrue(sandbox['build_message'](recipient=context(lang)['recipients'][0],platform_url='https://school.example',language=lang).startswith(heading))
  tree=ast.parse((PROJECT/'app/routers/web/planning/month_plan_web.py').read_text())
  route=next(node for node in tree.body if isinstance(node,ast.AsyncFunctionDef) and node.name=='school_monthly_whatsapp')
  call=next(node for node in ast.walk(route) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='open_recipient_whatsapp')
  language=next(keyword.value for keyword in call.keywords if keyword.arg=='language')
  self.assertEqual(ast.unparse(language),'resolve_language(request, user)')

if __name__=='__main__':unittest.main()
