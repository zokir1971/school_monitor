"""Offline rating rendering and route forwarding; no DB or rating writes."""
import ast,asyncio,copy,re,unittest
from html.parser import HTMLParser
from types import SimpleNamespace as NS
from fastapi import HTTPException
from test_ui_language import environment,request,PROJECT
from app.core.i18n import translate,resolve_language
from app.modules.monitoring.monitoring_dto import StaffMonitoringTotalsDTO
class RatingHTML(HTMLParser):
 def __init__(self):super().__init__();self.part=None;self.cell=None;self.cells={'tbody':[],'tfoot':[]};self.widths=[];self.visible=[];self.skip=False
 def handle_starttag(self,tag,attrs):
  d=dict(attrs)
  if tag in self.cells:self.part=tag
  if tag=='td' and self.part:self.cell=[]
  if d.get('class')=='progress-bar':self.widths.append(d.get('style'))
  if tag in ['script','style']:self.skip=True
 def handle_data(self,data):
  if not self.skip:self.visible.append(data)
  if self.cell is not None:self.cell.append(data)
 def handle_endtag(self,tag):
  if tag=='td' and self.cell is not None:self.cells[self.part].append(' '.join(' '.join(self.cell).split()));self.cell=None
  if tag in self.cells:self.part=None
  if tag in ['script','style']:self.skip=False

def row(rank=1,percent=50):return NS(rank=rank,full_name='DATA <PERSON>',position_text='DATA <POSITION>',assigned_count=4,primary_assignment_count=2,co_executor_assignment_count=2,completed_count=1,final_document_count=1,assigned_report_count=4,completed_report_count=2,pending_report_count=1,waived_report_count=1,report_completion_percent=percent,average_score_per_task=0.75,total_score=3)
def context(lang,filled=True,percent=50):
 totals=StaffMonitoringTotalsDTO(staff_count=1,unique_task_count=4,assignment_count=4,primary_assignment_count=2,co_executor_assignment_count=2,tasks_with_coexecutors_count=2,completed_tasks_with_coexecutors_count=1,completed_count=1,final_document_count=1,assigned_report_count=4,completed_report_count=2,pending_report_count=1,waived_report_count=1,report_completion_percent=percent,average_score_per_staff=3.0,total_score=3) if filled else StaffMonitoringTotalsDTO()
 return dict(request=request(lang),user={'role':'school_admin','full_name':'DATA USER'},school_name='DATA <SCHOOL>',academic_year='2026–2027',rating_rows=[row(1,percent),row(4,percent)] if filled else [],totals=totals,selected_month_plan_id=22,selected_direction_id=7)
def render(data):return environment().get_template('monitoring/staff_rating.html').render(**data)
class StaffRatingI18nTests(unittest.TestCase):
 def test_metrics_order_and_progress_identical(self):
  for percent in [0,50,100,125]:
   parsed=[]
   for lang in ['ru','kk']:
    data=context(lang,percent=percent);before=copy.deepcopy((data['rating_rows'],data['totals']));html=render(data);p=RatingHTML();p.feed(html);parsed.append(p)
    self.assertIn('DATA &lt;PERSON&gt;',html);self.assertIn('DATA &lt;POSITION&gt;',html);self.assertIn('DATA &lt;SCHOOL&gt;',html);self.assertEqual((data['rating_rows'],data['totals']),before)
    self.assertEqual(p.widths,[f'width: {min(percent,100)}%;']*2)
    for offset,rank in [(0,'1'),(12,'4')]:
     cells=p.cells['tbody'][offset:offset+12]
     self.assertEqual(cells[0],rank);self.assertEqual(cells[2:9],['4','1','1','4','2','1','1']);self.assertEqual(cells[9],f'2 / 4 · {percent}%');self.assertEqual(cells[10:],['0.75','3'])
    text=' '.join(p.visible)
    for code in ['PRIMARY','COMPLETED','PENDING','WAIVED']:self.assertNotIn(code,text)
    self.assertIn('ВШК' if lang=='ru' else 'МІБ',text)
   self.assertEqual([c for i,c in enumerate(parsed[0].cells['tbody']) if i%12!=1],[c for i,c in enumerate(parsed[1].cells['tbody']) if i%12!=1]);self.assertEqual(parsed[0].cells['tfoot'][1:],parsed[1].cells['tfoot'][1:])
 def test_empty_and_zero_values(self):
  for lang in ['ru','kk']:
   data=context(lang,False);html=render(data);p=RatingHTML();p.feed(html);self.assertIn(translate('Для выбранного периода данные исполнителей отсутствуют.',lang),html);self.assertEqual(p.cells['tbody'],[]);self.assertEqual(p.widths,[])
   self.assertEqual(data['totals'].total_score,0);self.assertEqual(data['totals'].report_completion_percent,0.0)
 def test_full_captions_and_rules(self):
  for lang in ['ru','kk']:
   html=render(context(lang))
   for source in ['Рейтинг исполнителей','Участий в задачах','Личное выполнение отчётов','Средний балл за участие','Назначено отчётов','Выполнено отчётов']:self.assertIn(translate(source,lang),html)
   self.assertIn('1 балл',html);self.assertIn('0 балл',html)
   self.assertIn('Ответственный:' if lang=='ru' else 'Жауапты:',html)
 def test_route_filters_access_result_and_missing_plan(self):
  path=PROJECT/'app/routers/web/monitoring/staff_rating_web.py';tree=ast.parse(path.read_text());function=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='staff_monitoring_rating_page');function.decorator_list=[]
  for a in function.args.args:a.annotation=None
  function.returns=None;function.args.defaults=[ast.Constant(None) for _ in function.args.defaults]
  module=ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[]))
  for lang in ['ru','kk']:
   for missing in [False,True]:
    calls=[];data=context(lang);page=NS(rating_rows=data['rating_rows'],totals=data['totals'],selected_month_plan_id=22,selected_direction_id=7)
    async def get_active(db,**kw):calls.append(('plan',kw));return None if missing else NS(id=7,academic_year='2026–2027',school=NS(name='DATA SCHOOL'))
    async def get_page(db,**kw):calls.append(('page',kw));return page
    scope=dict(SchoolPlanStatisticsService=NS(get_active_school_plan=get_active),StaffMonitoringService=NS(get_page_data=get_page),HTTPException=HTTPException,translate=translate,resolve_language=resolve_language,templates=object(),render=lambda templates,req,name,data:(name,data))
    exec(compile(module,str(path),'exec'),scope)
    coroutine=scope['staff_monitoring_rating_page'](request(lang),month_plan_id=22,direction_id=7,db=object(),user=NS(school_id=2,ui_language=lang))
    if missing:
     with self.assertRaises(HTTPException) as caught:asyncio.run(coroutine)
     self.assertEqual(caught.exception.status_code,404);self.assertEqual(caught.exception.detail,translate('Активный план школы не найден',lang));self.assertEqual(len(calls),1)
    else:
     name,values=asyncio.run(coroutine);self.assertEqual(name,'monitoring/staff_rating.html');self.assertIs(values['totals'],page.totals);self.assertIs(values['rating_rows'],page.rating_rows);self.assertEqual(calls,[('plan',{'school_id':2}),('page',{'school_plan_id':7,'academic_year':'2026–2027','month_plan_id':22,'direction_id':7})])
if __name__=='__main__':unittest.main()
