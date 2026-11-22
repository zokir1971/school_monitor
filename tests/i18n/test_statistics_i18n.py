"""Offline statistics UI checks; no DB queries, calculation changes, or CDN requests."""
import ast,asyncio,copy,json,re,subprocess,unittest
from html.parser import HTMLParser
from types import SimpleNamespace as NS
from fastapi import HTTPException
from test_ui_language import environment,request,PROJECT
from app.core.i18n import translate,resolve_language
PAGES=['statistics_planning','statistics_execution','staff_statistics']
class Parsed(HTMLParser):
 def __init__(self):super().__init__();self.cells=[];self.cell=None;self.links=[];self.styles=[];self.classes=[]
 def handle_starttag(self,tag,attrs):
  d=dict(attrs)
  if tag=='td':self.cell=[]
  if tag=='a':self.links.append(d.get('href'))
  if 'style' in d:self.styles.append(d['style'])
  if 'class' in d and not d['class'].startswith('ui-language'):self.classes.append(d['class'])
 def handle_data(self,data):
  if self.cell is not None:self.cell.append(data)
 def handle_endtag(self,tag):
  if tag=='td' and self.cell is not None:self.cells.append(' '.join(' '.join(self.cell).split()));self.cell=None

def context(lang,filled=True,selected=True,zero=False):
 n=0 if zero else 8
 common=dict(direction_name='DATA <DIRECTION>',annual_planned_count=n,included_count=n,remaining_count=0,planned_count=n,assigned_count=n,completed_count=4 if n else 0,not_completed_count=4 if n else 0,reviewed_count=2 if n else 0,planning_percent=100 if n else 0,completion_percent=50 if n else 0,review_percent=50 if n else 0)
 row=NS(**common);totals=NS(**common)
 month=NS(month_plan_id=23,year=2026,month_name='Қазан (Октябрь)',plan_status_label='В работе',**{k:v for k,v in common.items() if k!='direction_name'})
 place={'ped_council_count':1,'method_council_count':2,'director_council_count':3,'administrative_council_count':4,'method_assoc_count':5,'total_review_places_count':15}
 if zero:place={k:0 for k in place}
 return dict(request=request(lang),user={'role':'school_admin','full_name':'DATA USER'},school_name='DATA <SCHOOL>',academic_year='2026–2027',staff_name='DATA <PERSON>',staff_position='DATA <POSITION>',total_planned_count=n,period_stats=[NS(direction_name='DATA <DIRECTION>',month_count=1,months_count=2,monthly_count=3,quarter_count=4,all_year_count=5)] if filled else [],planned_stats=[NS(direction_name='DATA <DIRECTION>',planned_count=n)] if filled else [],review_place_stats=[NS(direction_name='DATA <DIRECTION>',**place)] if filled else [],review_place_totals=place,comparison_summary=NS(total_directions=2,matched_count=1,mismatched_count=1),comparison_stats=[NS(direction_name='DATA <MATCH>',period_total=n,planned_count=n,review_place_total=n,diff=0,is_match=True),NS(direction_name='DATA <MISMATCH>',period_total=n,planned_count=n,review_place_total=n+1,diff=-1,is_match=False)] if filled else [],annual_stats=[row] if filled else [],annual_totals=totals,monthly_stats=[month] if filled else [],monthly_totals=totals,selected_month=month if selected else None,month_direction_stats=[row] if filled else [],month_direction_totals=totals)
def render(page,data):return environment().get_template('statistics/'+page+'.html').render(**data)
class StatisticsI18nTests(unittest.TestCase):
 def test_tables_metrics_links_and_author_data(self):
  for page in PAGES:
   for zero in [False,True]:
    parsed=[]
    for lang in ['ru','kk']:
     data=context(lang,zero=zero);before=copy.deepcopy({k:v for k,v in data.items() if k not in ['request']});html=render(page,data);p=Parsed();p.feed(html);parsed.append(p)
     self.assertIn('DATA &lt;SCHOOL&gt;',html);self.assertIn('DATA &lt;DIRECTION&gt;',html);self.assertIn('МІБ' if lang=='kk' else 'ВШК',html)
     for k,v in before.items():self.assertEqual(data[k],v)
     if page=='staff_statistics':self.assertIn('DATA &lt;PERSON&gt;',html);self.assertIn('DATA &lt;POSITION&gt;',html)
     if page!='statistics_planning':self.assertIn('Қазан' if lang=='kk' else 'Октябрь',html);self.assertIn(translate('В работе',lang),html)
    # Only first column captions/month/status words may differ; numeric cells stay exact.
    numeric=lambda p:[c for c in p.cells if re.fullmatch(r'-?\d+(?:\.\d+)?%?',c)]
    self.assertEqual(numeric(parsed[0]),numeric(parsed[1]));self.assertEqual(parsed[0].links,parsed[1].links);self.assertEqual(parsed[0].styles,parsed[1].styles);self.assertEqual(parsed[0].classes,parsed[1].classes)
    if page=='statistics_planning':self.assertIn('width: 0.0%;' if zero else 'width: 100.0%;',parsed[0].styles)
 def test_chart_labels_and_payload(self):
  captures=[]
  for lang in ['ru','kk']:
   data=context(lang);html=render(PAGES[0],data);script=next(s for s in re.findall(r'<script\b[^>]*>(.*?)</script>',html,re.S) if 'new Chart' in s)
   js='const vm=require("vm");let result;vm.runInNewContext('+json.dumps(script)+',{document:{getElementById(){return {}}},Chart:function(target,config){result=config},ChartDataLabels:{}});process.stdout.write(JSON.stringify(result));'
   r=subprocess.run(['node','-e',js],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr);config=json.loads(r.stdout);captures.append(config)
   self.assertEqual(config['data']['datasets'][0]['data'],[1,2,3,4,5]);self.assertEqual(config['data']['labels'],[translate(k,lang) for k in ['Пед.кеңес','Әд.кеңес','ДЖ.кеңес','Әк.кеңес','ӘБ.отырысы']]);self.assertEqual(config['data']['datasets'][0]['label'],translate('Количество задач',lang))
  self.assertEqual(captures[0]['options'],captures[1]['options']);self.assertEqual(captures[0]['data']['datasets'][0]['backgroundColor'],captures[1]['data']['datasets'][0]['backgroundColor'])
 def test_empty_selected_month_and_zero_assigned_link(self):
  for lang in ['ru','kk']:
   for page in PAGES:
    for selected in [False,True]:
     html=render(page,context(lang,filled=False,selected=selected,zero=True));self.assertNotIn('DATA &lt;DIRECTION&gt;',html)
     if page=='statistics_execution':self.assertIn(translate('Месячные планы для выбранного годового плана пока не сформированы.',lang),html)
     if page=='staff_statistics':self.assertIn(translate('Для текущего учебного года месячные планы пока не сформированы.',lang),html)
   data=context(lang,zero=True);p=Parsed();p.feed(render('staff_statistics',data));self.assertFalse(any('month_plan_id=23' in (s or '') for s in p.links))
   data=context(lang);p=Parsed();p.feed(render('staff_statistics',data));self.assertTrue(any('month_plan_id=23#month-direction-statistics' in (s or '') for s in p.links))
 def test_statuses_comparison_and_fallback_labels(self):
  for lang in ['ru','kk']:
   for status in ['Черновик','Утверждён','В работе','Завершён','Архивный']:
    data=context(lang);data['monthly_stats'][0].plan_status_label=status;html=render('statistics_execution',data);self.assertIn(translate(status,lang),html)
   html=render('statistics_planning',context(lang));self.assertIn(translate('Совпадает',lang),html);self.assertIn(translate('Не совпадает',lang),html);self.assertIn('DATA &lt;MATCH&gt;',html);self.assertIn('DATA &lt;MISMATCH&gt;',html)
 def test_three_missing_plan_diagnostics(self):
  path=PROJECT/'app/routers/web/statistics/school_statistics_web.py';tree=ast.parse(path.read_text())
  for lang in ['ru','kk']:
   for name,source in [('school_plan_statistics_page','Активный план школы не найден'),('school_execution_statistics_page','План школы не найден'),('staff_statistics_page','Активный план школы не найден.')]:
    fn=copy.deepcopy(next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name==name));fn.decorator_list=[];fn.returns=None
    for a in fn.args.args:a.annotation=None
    fn.args.defaults=[ast.Constant(None) for _ in fn.args.defaults];module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]));calls=[]
    async def active(db,**kwargs):calls.append(kwargs);return None
    scope=dict(SchoolPlanStatisticsService=NS(get_active_school_plan=active),HTTPException=HTTPException,translate=translate,resolve_language=resolve_language);exec(compile(module,str(path),'exec'),scope)
    with self.assertRaises(HTTPException) as caught:asyncio.run(scope[name](request(lang),db=object(),user=NS(school_id=2,ui_language=lang)))
    self.assertEqual(caught.exception.status_code,404);self.assertEqual(caught.exception.detail,translate(source,lang));self.assertEqual(calls,[{'school_id':2}])
if __name__=='__main__':unittest.main()
