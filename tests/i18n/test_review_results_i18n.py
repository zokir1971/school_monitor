"""Offline review results rendering; no review writes or document downloads."""
import copy,json,re,subprocess,unittest
from datetime import date,datetime
from html.parser import HTMLParser
from types import SimpleNamespace as NS
from test_ui_language import environment,request
from app.core.i18n import translate
from app.core.review_results_i18n import result_message,result_label,protocol_label
from app.modules.planning.enums import PlanItemStatus,ReviewPlace
class Fields(HTMLParser):
 def __init__(self):super().__init__();self.fields=[];self.links=[]
 def handle_starttag(self,tag,attrs):
  if tag in ['form','input','select','option','button']:self.fields.append((tag,tuple((k,v) for k,v in attrs if k not in ['class','title','placeholder','aria-label','aria-pressed'])))
  if tag=='a':self.links.append(dict(attrs).get('href'))
def document(n):return NS(title='DATA <DOC TITLE>',file_name='DATA <FILE>.pdf',view_url=f'/staff/reviews/documents/{n}/view',download_url=f'/staff/reviews/documents/{n}/download')
def item(reviewed=True):
 return NS(month_item_id=81,task_name='DATA <TASK>',task_goal='DATA GOAL',responsible_name='DATA PERSON',participation_label='Жауапты, Қосалқы орындаушы',planned_period_text='DATA PERIOD',task_status='done',task_status_label='Орындалды',review_place='ped_council',is_reviewed=reviewed,review_count=2 if reviewed else 0,latest_review_status_label='Қаралды',latest_reviewed_at=datetime(2026,10,24,10,30),latest_protocol_number='DATA № 1',latest_protocol_date=date(2026,10,24),latest_review_comment='DATA <COMMENT>')
def context(lang,filled=True,reviewed=True):
 return dict(request=request(lang),user={'role':'school_admin','full_name':'DATA USER'},error=None,school_id=2,academic_year_label='2026–2027',selected_year=2026,selected_month=10,selected_review_place=ReviewPlace.PED_COUNCIL,selected_reviewed=reviewed,selected_task_review_id=7,available_years=[2026] if filled else [],available_months=[{'num':10,'label':'Қазан (Октябрь)'}],review_places=[{'value':p.value,'label':p.label_kz} for p in ReviewPlace],available_protocols=[{'id':7,'label':'Протокол №DATA № 1 от 24.10.2026'}],items=[item(reviewed)] if filled else [],total_count=1 if filled else 0,reviewed_count=int(bool(reviewed and filled)),not_reviewed_count=int(not reviewed and filled))
def detail_context(lang,filled=True,history=True,docs=True):
 data=context(lang);d=item();d.year=2026;d.month=10;d.review_place_label='Пед.кеңес';d.final_document=document(3) if docs else None;d.execution_reports=[document(4)] if docs else []
 h=NS(review_place_label='Пед.кеңес',status_label='Қаралды',reviewed_at=datetime(2026,10,24,10,30),reviewed_by_name='DATA REVIEWER',protocol_number='DATA № 1',protocol_date=date(2026,10,24),protocol_document=document(5) if docs else None,comment='DATA <HISTORY COMMENT>')
 d.history=[h,copy.deepcopy(h)] if history else [];data['detail']=d if filled else None;return data
def render(name,data):return environment().get_template('reviews/'+name+'.html').render(**data)
class ReviewResultsI18nTests(unittest.TestCase):
 def test_list_filters_links_and_data(self):
  for filled in [False,True]:
   for reviewed in [None,False,True]:
    parsers=[]
    for lang in ['ru','kk']:
     data=context(lang,filled,reviewed);before=copy.deepcopy(data['items']);html=render('review_results_list',data);p=Fields();p.feed(html);parsers.append(p)
     self.assertIn(translate('Результаты рассмотрения задач',lang),html);self.assertIn('Октябрь' if lang=='ru' else 'Қазан',html)
     self.assertIn('Протокол №DATA № 1 от 24.10.2026' if lang=='ru' else 'Хаттама №DATA № 1 күні 24.10.2026',html)
     if filled:
      for text in ['DATA &lt;TASK&gt;','DATA PERSON','DATA PERIOD',translate('Орындалды',lang),translate('Жауапты',lang)]:self.assertIn(text,html)
     self.assertEqual(data['items'],before)
    self.assertEqual(parsers[0].fields,parsers[1].fields);self.assertEqual(parsers[0].links,parsers[1].links)
 def test_detail_history_documents_and_back_url(self):
  for filled in [False,True]:
   for history in [False,True]:
    for docs in [False,True]:
     parsers=[]
     for lang in ['ru','kk']:
      data=detail_context(lang,filled,history,docs);before=copy.deepcopy(data['detail']);html=render('review_result_detail',data);p=Fields();p.feed(html);parsers.append(p)
      self.assertIn(translate('Результат рассмотрения задачи',lang),html)
      if filled:
       self.assertIn('DATA &lt;TASK&gt;',html);self.assertIn('DATA PERSON',html);self.assertIn('DATA PERIOD',html)
       self.assertTrue(any('school_id=2' in (link or '') and 'year=2026' in link and 'month=10' in link and 'review_place=ped_council' in link for link in p.links))
       if docs:self.assertIn('DATA &lt;DOC TITLE&gt;',html);self.assertIn('DATA &lt;FILE&gt;.pdf',html)
       if history:self.assertIn('DATA &lt;HISTORY COMMENT&gt;',html);self.assertIn('DATA REVIEWER',html);self.assertIn(translate('Қаралды',lang),html)
      self.assertEqual(data['detail'],before)
     self.assertEqual(parsers[0].links,parsers[1].links)
 def test_scoped_filter_script(self):
  for lang in ['ru','kk']:
   html=render('review_results_list',context(lang));script=next(s for s in re.findall(r'<script\b[^>]*>(.*?)</script>',html,re.S) if 'reviewPlace.focus' in s)
   js='''const vm=require('vm');let submit,prevent=0,focus=0,alerts=[];const field={value:'',focus(){focus++}};const form={addEventListener(e,f){submit=f}};
vm.runInNewContext(SCRIPT,{document:{querySelector(q){if(q==='.filters-form')return form;if(q==='select[name="review_place"]')return field;throw Error('wrong form '+q)}},alert(s){alerts.push(s)}});submit({preventDefault(){prevent++}});if(prevent!==1||focus!==1||alerts.length!==1)throw Error('missing place');field.value='ped_council';submit({preventDefault(){prevent++}});if(prevent!==1||alerts.length!==1)throw Error('valid place blocked');process.stdout.write(alerts[0]);'''.replace('SCRIPT',json.dumps(script))
   result=subprocess.run(['node','-e',js],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout,translate('Для просмотра результатов необходимо выбрать место рассмотрения.',lang))
 def test_error_messages_and_unknown_data(self):
  for lang in ['ru','kk']:
   source='У пользователя нет доступа к результатам рассмотрения.'
   self.assertEqual(result_message(source,lang),translate(source,lang));self.assertNotIn('private',result_message('private <stack>',lang))
   self.assertEqual(result_label('DATA CUSTOM',lang),'DATA CUSTOM');self.assertEqual(protocol_label('DATA CUSTOM',lang),'DATA CUSTOM')
   for page,data in [('review_results_list',context(lang)),('review_result_detail',detail_context(lang))]:
    data['error']=source;self.assertIn(translate(source,lang),render(page,data))
 def test_protocol_number_and_fallbacks(self):
  for lang in ['ru','kk']:
   number='A от 01.01.2020 / DATA <N>'
   text=protocol_label('Протокол №'+number+' от 24.10.2026',lang);self.assertIn('№'+number,text);self.assertTrue(text.endswith('24.10.2026'))
   self.assertEqual(protocol_label('Протокол',lang),translate('Протокол',lang))
   data=detail_context(lang);data['detail'].task_name=None;data['detail'].responsible_name=None;data['detail'].task_status_label=None
   html=render('review_result_detail',data);self.assertIn(translate('Не определён',lang),html);self.assertIn(translate('Не указан',lang),html)
if __name__=='__main__':unittest.main()
