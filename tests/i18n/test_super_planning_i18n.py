"""Read-only template rendering tests; never import DOCX, delete or create plan records."""
import copy,json,re,subprocess,unittest
from html.parser import HTMLParser
from types import SimpleNamespace as NS
from test_ui_language import environment,request
from app.core.i18n import translate
from app.core.super_planning_i18n import super_planning_feedback,SUPER_PLANNING_ERRORS
PAGES=['directions','directions_add','builder']
class Fields(HTMLParser):
 def __init__(self):super().__init__();self.fields=[];self.links=[];self.confirmations=[]
 def handle_starttag(self,tag,attrs):
  data=dict(attrs)
  if tag in ['form','input','select','option','textarea','button','fieldset']:self.fields.append((tag,tuple((k,v) for k,v in attrs if k not in ['placeholder','title','aria-label','class','aria-pressed','onsubmit'])))
  if tag=='a':self.links.append(data.get('href'))
  if 'onsubmit' in data:self.confirmations.append(data['onsubmit'])
def context(lang,filled=True,active=True):
 direction=NS(id=5,short_title='DATA <SHORT>',full_title='DATA <FULL>')
 template=NS(id=7,name='DATA <TEMPLATE>',academic_year='2026–2027',is_active=True)
 row4=NS(id=81,control_object='DATA <OBJECT>',risk_text='DATA <RISK>',decision_text='DATA <DECISION>')
 row11=NS(id=82,topic='DATA <TOPIC>',goal='DATA <GOAL>',control_object='DATA <OBJECT>',control_type='DATA <TYPE>',methods='DATA <METHOD>',deadlines='DATA <DEADLINE>',responsibles='DATA <RESPONSIBLE>',review_place='DATA <REVIEW>',management_decision='DATA <DECISION>',second_control='DATA <SECOND>')
 return dict(request=request(lang),user={'role':'superuser','full_name':'DATA USER'},error=None,success=None,directions=[direction] if filled else [],active_template_id=7 if active else None,active_template=template if active else None,templates=[template] if filled else [],selected_template_id=7 if active else None,selected_direction_id=5 if filled else None,selected_template=template if active else None,selected_direction=direction if filled else None,rows4=[row4] if filled else [],rows11=[row11] if filled else [],form=NS(short_title='DATA "SHORT"',full_title='DATA <FULL FORM>',is_active='false'))
def render(page,data):return environment().get_template('planning/super/'+page+'.html').render(**data)
class SuperPlanningI18nTests(unittest.TestCase):
 def test_forms_values_links_and_authored_plan_data(self):
  for page in PAGES:
   for filled in [False,True]:
    for active in [False,True]:
     parsers=[]
     for lang in ['ru','kk']:
      data=context(lang,filled,active);before=copy.deepcopy({k:v for k,v in data.items() if k!='request'});html=render(page,data);p=Fields();p.feed(html);parsers.append(p)
      for k,v in before.items():self.assertEqual(data[k],v)
      if page=='directions' and filled:self.assertIn('DATA &lt;SHORT&gt;',html);self.assertIn('DATA &lt;FULL&gt;',html)
      if page=='directions_add':self.assertIn('DATA &#34;SHORT&#34;',html);self.assertIn('DATA &lt;FULL FORM&gt;',html)
      if page=='builder' and active and filled:
       for name in ['OBJECT','RISK','DECISION','TOPIC','GOAL','TYPE','METHOD','DEADLINE','RESPONSIBLE','REVIEW','SECOND']:self.assertIn('DATA &lt;'+name+'&gt;',html)
      if page!='directions_add' or not active:self.assertIn('МІБ' if lang=='kk' else 'ВШК',html)
     self.assertEqual(parsers[0].fields,parsers[1].fields);self.assertEqual(parsers[0].links,parsers[1].links)
 def test_delete_confirmations_are_valid_localized_js(self):
  for page in ['directions','builder']:
   for lang in ['ru','kk']:
    p=Fields();p.feed(render(page,context(lang)));self.assertEqual(len(p.confirmations),1 if page=='directions' else 2)
    source='const handlers='+json.dumps(p.confirmations)+''';let messages=[];for(const answer of [false,true])for(const code of handlers){let captured;const result=new Function('confirm',code)(message=>{captured=message;return answer});if(result!==answer)throw Error('confirmation bypass');messages.push(captured)}process.stdout.write(JSON.stringify(messages));'''
    result=subprocess.run(['node','-e',source],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr);key='Удалить направление?' if page=='directions' else 'Удалить строку?';self.assertEqual(json.loads(result.stdout),[translate(key,lang)]*(len(p.confirmations)*2))
 def test_import_feedback_counts_errors_and_unknown_details(self):
  for lang in ['ru','kk']:
   value='Импорт завершён: объектов=12, задач=34';expected=translate('Импорт завершён: объектов={objects}, задач={tasks}',lang).format(objects='12',tasks='34');self.assertEqual(super_planning_feedback(value,lang),expected)
   data=context(lang);data['success']=value;self.assertIn(expected,render('builder',data))
   for source in SUPER_PLANNING_ERRORS:
    self.assertEqual(super_planning_feedback(source,lang),translate(source,lang));data['error']=source;self.assertIn(translate(source,lang),render('builder',data))
   source=SUPER_PLANNING_ERRORS[-1];self.assertEqual(super_planning_feedback('Ошибка импорта: '+source,lang),translate(source,lang))
   for error in ['private <stack>','Ошибка импорта: private <stack>']:self.assertNotIn('private',super_planning_feedback(error,lang))
 def test_import_warning_and_technical_ui_labels(self):
  for lang in ['ru','kk']:
   html=render('builder',context(lang));self.assertIn(translate('Внимание: импорт удалит старые строки таблиц №+3 и №+10 для выбранного направления и загрузит новые.',lang),html);self.assertIn(translate('Импортировать (REPLACE)',lang),html);self.assertNotIn('(REPLACE)',html);self.assertNotIn('(Row11)',html)
   html=render('directions_add',context(lang,active=False));self.assertNotIn('(plan_templates)',html);self.assertIn('disabled',html)
if __name__=='__main__':unittest.main()
