"""Offline review form and JS validation tests; never upload a protocol or save reviews."""
import copy,json,re,subprocess,unittest
from html.parser import HTMLParser
from types import SimpleNamespace as NS
from test_ui_language import environment,request,PROJECT
from app.core.i18n import translate
from app.core.task_review_i18n import TASK_REVIEW_ERRORS,TASK_REVIEW_DETAIL_ERRORS,task_review_message
from app.modules.planning.enums import PlanItemStatus,ReviewPlace
class Fields(HTMLParser):
 def __init__(self):super().__init__();self.fields=[]
 def handle_starttag(self,tag,attrs):
  d=dict(attrs)
  if tag not in ['form','input','select','option','textarea','button']:return
  skip={'class','title','placeholder','aria-label','aria-pressed'}
  if d.get('id') in ['academic-year','selected-review-place','selected-method-association']:skip.add('value') # unnamed display fields
  self.fields.append((tag,tuple((k,v) for k,v in attrs if k not in skip)))
def task(n,status,enabled=True):return NS(month_item_id=n,task_name='DATA <TASK>',responsible_name='DATA PERSON',planned_period_text='DATA PERIOD',status=status.value,status_label=status.label_kz,can_select=enabled,expected_result_label='Будет рассмотрена' if status==PlanItemStatus.DONE else 'Останется окончательно не выполненной')
def context(lang,place='ped_council',filled=True,overdue=True):
 return dict(request=request(lang),user={'role':'school_admin','full_name':'DATA USER'},error=None,school_plan_id=7,academic_year_label='2026–2027',selected_review_place=ReviewPlace(place) if place else None,review_places=list(ReviewPlace),method_associations=[NS(id=5,name='DATA <ASSOCIATION>')],form_data={'month_item_ids':[81],'protocol_number':'DATA "№1"','protocol_date':'2026-10-24','comment':'DATA <COMMENT>','method_association_id':'5'},tasks=[task(81,PlanItemStatus.DONE),task(82,PlanItemStatus.NOT_EXECUTED),task(83,PlanItemStatus.IN_PROGRESS,False)] if filled else [],overdue_tasks=[task(84,PlanItemStatus.TODO),task(85,PlanItemStatus.IN_PROGRESS)] if overdue else [])
def render(data):return environment().get_template('reviews/task_review.html').render(**data)
class TaskReviewI18nTests(unittest.TestCase):
 def test_form_payloads_and_restored_data(self):
  for place in [None,'ped_council','method_assoc']:
   for filled in [False,True]:
    for overdue in [False,True]:
     parsers=[]
     for lang in ['ru','kk']:
      data=context(lang,place,filled,overdue);before=copy.deepcopy({k:data[k] for k in ['tasks','overdue_tasks','form_data','method_associations']});html=render(data);p=Fields();p.feed(html);parsers.append(p)
      self.assertIn(translate('Рассмотрение задач',lang),html);self.assertIn('DATA &lt;ASSOCIATION&gt;',html)
      if filled and place:
       self.assertIn('DATA &lt;TASK&gt;',html);self.assertIn('DATA &lt;COMMENT&gt;',html);self.assertIn('DATA &#34;№1&#34;',html);self.assertIn(translate('Будет рассмотрена',lang),html)
      for k,v in before.items():self.assertEqual(data[k],v)
     self.assertEqual(parsers[0].fields,parsers[1].fields)
 def test_real_script_selection_validation_confirmation(self):
  for place in ['ped_council','method_assoc']:
   for lang in ['ru','kk']:
    html=render(context(lang,place));script=next(s for s in re.findall(r'<script\b[^>]*>(.*?)</script>',html,re.S) if 'MAX_PROTOCOL_FILE_SIZE' in s)
    result=subprocess.run(['node',str(PROJECT/'tests/i18n/task_review_dom.js')],input=json.dumps({'script':script,'place':place}),capture_output=True,text=True)
    self.assertEqual(result.returncode,0,result.stderr);data=json.loads(result.stdout)
    for source in ['Выберите хотя бы одну просроченную задачу.','Выберите хотя бы одну задачу для рассмотрения.','Укажите номер протокола.','Укажите дату протокола.','Выберите файл протокола.','Размер файла протокола не должен превышать 20 МБ.','Разрешены только файлы PDF, DOC и DOCX.']:self.assertIn(translate(source,lang),data['alerts'])
    self.assertIn(translate('Перевести выбранные задачи в статус «Не исполнено»: ',lang)+'2?',data['confirms'])
    self.assertEqual(data['confirms'][-1],translate('Сохранить рассмотрение для выбранных задач: ',lang)+'1'+translate('?\nПротокол: ',lang)+'DATA <FILE> {p0}.PDF');self.assertEqual(data['count'],'2')
 def test_script_without_batch_or_overdue_sections(self):
  for lang in ['ru','kk']:
   html=render(context(lang,None,False,False));script=next(s for s in re.findall(r'<script\b[^>]*>(.*?)</script>',html,re.S) if 'MAX_PROTOCOL_FILE_SIZE' in s)
   source='const vm=require("vm");vm.runInNewContext('+json.dumps(script)+',{document:{addEventListener(e,f){f()},getElementById(){return null},querySelector(){return null}},window:{},alert(){throw Error("unexpected alert")}});'
   result=subprocess.run(['node','-e',source],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr)
 def test_known_errors_dynamic_details_and_escaping(self):
  for lang in ['ru','kk']:
   for source in TASK_REVIEW_ERRORS:self.assertEqual(task_review_message(source,lang),translate(source,lang))
   for prefix,source in TASK_REVIEW_DETAIL_ERRORS.items():
    value=prefix+'81, DATA <TASK> {items}';expected=translate(source,lang).format(items='81, DATA <TASK> {items}');self.assertEqual(task_review_message(value,lang),expected)
    data=context(lang);data['error']=value;html=render(data);self.assertIn('81, DATA &lt;TASK&gt; {items}',html)
   self.assertNotIn('private',task_review_message('private <stack>',lang))
   self.assertEqual(task_review_message('Недопустимый статус задачи ID=81: todo',lang),translate('Недопустимый статус выбранной задачи.',lang))
 def test_success_feedback_and_terminology(self):
  for lang in ['ru','kk']:
   for code,source in [('reviewed','Рассмотрение успешно сохранено.'),('marked_not_executed','Просроченные задачи переведены в статус «Не исполнено».')]:
    data=context(lang);data['request'].scope['query_string']=f'success={code}&reviewed_count=2&updated_count=3'.encode();html=render(data);self.assertIn(translate(source,lang),html)
   html=render(context(lang));self.assertIn('активного плана ВШК' if lang=='ru' else 'белсенді МІБ жоспарының',html)
if __name__=='__main__':unittest.main()
