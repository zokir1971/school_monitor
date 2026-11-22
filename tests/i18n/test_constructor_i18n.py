"""Constructor localization tests use a mock DOM, never save templates or call a DB."""
import copy,json,re,subprocess,unittest
from types import SimpleNamespace as NS
from html.parser import HTMLParser
from test_ui_language import environment,request,PROJECT
from app.core.i18n import translate
from app.core.reports_i18n import reports_message
PAGES=['lesson_observation.html','checking_notebooks_table.html']
TITLE='DATA "TITLE" O\'Name <&> {p0} &quot;'
CRITERION='DATA "CRITERION" O\'Name <&> {p0}'
class Fields(HTMLParser):
 def __init__(self):super().__init__();self.fields=[]
 def handle_starttag(self,tag,attrs):
  data=dict(attrs)
  if tag=='input' and 'disabled' in data and not data.get('name'):return
  if tag in ['form','input','textarea','select','option','button']:self.fields.append((tag,tuple((k,v) for k,v in attrs if k not in ['title','placeholder','aria-label','class','aria-pressed'])))

def context(lang,page,editing=True):
 criteria=[{'key':'custom_9','label_kz':CRITERION,'scores':{str(i):{'label_kz':f'DATA SCORE {i}'} for i in range(3)}},{'key':'criterion_1','label_kz':'SECOND CRITERION','scores':{str(i):{'label_kz':f'SECOND SCORE {i}'} for i in range(3)}}]
 rating={'levels':[{'from':0,'to':100,'label_kz':'DATA RATING'}]}
 lesson={'report_code':'lesson_observation','info_fields':['teacher_name','theme'],'sections':[{'title':TITLE,'criteria':[{'order':1,'text':CRITERION,'max_score':3},{'order':2,'text':'SECOND CRITERION','max_score':3}]}],'score_scale':[0,1,2,3],'show_total_score':False,'max_score':6}
 notebook={'type':'checking_notebooks_table','criteria':criteria,'rating':rating,'info_fields':['school_name','teacher_name']}
 return dict(request=request(lang),user={'role':'school_staff','full_name':'DATA USER'},template=NS(id=8,title=TITLE,description='DATA DESCRIPTION') if editing else None,schema=lesson if page==PAGES[0] else notebook,month_item_id=9,selected_report_id=21,report_code='checking_notebooks_table' if page==PAGES[1] else 'lesson_observation',report_label='Дәптер тексеру кестесі',error=None,criteria=criteria,default_criteria=criteria,info_fields=['school_name','teacher_name'],rating=rating)

class ConstructorI18nTests(unittest.TestCase):
 def test_pages_and_form_values(self):
  for page in PAGES:
   for editing in [False,True]:
    with self.subTest(page=page,editing=editing):
     texts=[]
     for lang in ['ru','kk']:
      data=context(lang,page,editing);before=copy.deepcopy(data['schema'])
      text=environment().get_template('staff/reports/user_templates/constructors/'+page).render(**data)
      self.assertEqual(data['schema'],before);self.assertIn(f'<html lang="{lang}">',text);texts.append(text)
     fields=[]
     for text in texts:
      parsed=Fields();parsed.feed(text);fields.append(parsed.fields);self.assertNotIn('value="'+TITLE+'"',text)
     self.assertEqual(fields[0],fields[1])
     if editing:self.assertIn('DATA DESCRIPTION',texts[0]);self.assertIn('DATA DESCRIPTION',texts[1])
     self.assertIn(translate('Редактировать шаблон' if editing else 'Создать шаблон','ru'),texts[0])
     self.assertIn(translate('Редактировать шаблон' if editing else 'Создать шаблон','kk'),texts[1])

 def run_dom(self,page,lang,schema=None):
  data=context(lang,page)
  if schema is not None:data['schema']=schema
  html=environment().get_template('staff/reports/user_templates/constructors/'+page).render(**data)
  scripts=re.findall(r'<script\b[^>]*>(.*?)</script>',html,re.S)
  script=next(s for s in scripts if 'function collectTemplateData' in s or 'function buildCheckingNotebooksSchema' in s)
  messages=json.loads(environment().from_string('{{ ui_messages()|tojson }}').render(request=request(lang)))
  args=dict(mode='lesson' if page==PAGES[0] else 'notebook',schema=data['schema'],criteria=data['criteria'],info_fields=data['info_fields'],script=script,messages=messages)
  result=subprocess.run(['node',str(PROJECT/'tests/i18n/constructor_dom.js')],input=json.dumps(args),text=True,capture_output=True)
  self.assertEqual(result.returncode,0,result.stderr)
  return json.loads(result.stdout),data

 def test_lesson_round_trip_and_edits(self):
  results=[]
  for lang in ['ru','kk']:
   result,data=self.run_dom(PAGES[0],lang)
   self.assertEqual(result['first'],data['schema']);self.assertEqual(result['existing'],data['schema'])
   self.assertEqual(result['first']['info_fields'],['teacher_name','theme']);self.assertEqual(result['firstMax'],6)
   self.assertEqual(result['first']['sections'][0]['title'],TITLE);self.assertEqual(result['first']['sections'][0]['criteria'][0]['text'],CRITERION)
   self.assertEqual(result['afterAdd']['max_score'],9);self.assertEqual(result['afterRemove']['max_score'],6);self.assertEqual(result['afterSectionRemove']['max_score'],3)
   results.append(result)
  self.assertEqual(results[0],results[1])

 def test_empty_info_selection_is_restored(self):
  schema=context('ru',PAGES[0])['schema'];schema['info_fields']=[]
  for lang in ['ru','kk']:
   result,_=self.run_dom(PAGES[0],lang,schema)
   self.assertEqual(result['first']['info_fields'],[])

 def test_notebook_round_trip_defaults_and_keys(self):
  results=[]
  for lang in ['ru','kk']:
   result,data=self.run_dom(PAGES[1],lang)
   self.assertEqual(result['first'],data['schema'])
   self.assertEqual(result['afterEdit']['rating'],data['rating']);self.assertEqual(result['afterEdit']['info_fields'],data['info_fields'])
   self.assertEqual(result['afterEdit']['criteria'][0]['key'],'criterion_1')
   new=result['afterEdit']['criteria'][1]
   self.assertEqual(new['key'],'criterion_2');self.assertEqual(new['scores']['2']['label_kz'],'толық орындайды');self.assertEqual(new['scores']['1']['label_kz'],'ішінара орындайды');self.assertEqual(new['scores']['0']['label_kz'],'орындамайды')
   self.assertIn('Критерий атауы' if lang=='kk' else 'Название критерия',result['addedHtml'])
   results.append({k:v for k,v in result.items() if k!='addedHtml'})
  self.assertEqual(results[0],results[1])

 def test_custom_information_captions_and_errors(self):
  for lang in ['ru','kk']:
   data=context(lang,PAGES[1]);data['info_fields']=[{'key':'custom_field','label_kz':'DATA <FIELD> "LABEL"'}]
   text=environment().get_template('staff/reports/user_templates/constructors/'+PAGES[1]).render(**data)
   self.assertIn('DATA &lt;FIELD&gt; &#34;LABEL&#34;',text)
   self.assertIn('value="custom_field"',text)
   self.assertEqual(reports_message(request(lang),'Добавьте хотя бы один критерий.'),translate('Добавьте хотя бы один критерий.',lang))
if __name__=='__main__':unittest.main()
