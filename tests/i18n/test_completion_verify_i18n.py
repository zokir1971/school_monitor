"""Offline completion and QR display tests; no uploads, signing or DB writes."""
import copy,json,re,subprocess,unittest
from datetime import date,datetime
from html.parser import HTMLParser
from types import SimpleNamespace as NS
from test_ui_language import environment,request
from app.core.i18n import translate
from app.core.report_completion_i18n import completion_message,verification_message,review_places_label
from app.modules.reports.enums import TaskCompletionMode,TaskDocumentStatus,DocumentType
from app.modules.planning.enums import PlanItemStatus,ReviewPlace
class Fields(HTMLParser):
 def __init__(self):super().__init__();self.fields=[];self.links=[]
 def handle_starttag(self,tag,attrs):
  if tag in ['form','input','button','textarea']:self.fields.append((tag,tuple((k,v) for k,v in attrs if k not in ['placeholder','title','aria-label','class','aria-pressed'])))
  if tag=='a':self.links.append(dict(attrs).get('href'))
def context(lang,done=False,mode=None):
 return dict(request=request(lang),user={'role':'school_staff','full_name':'DATA USER'},task=NS(id=81,status=PlanItemStatus.DONE if done else PlanItemStatus.IN_PROGRESS,planned_start=date(2026,10,1),planned_end=date(2026,10,20)),task_topic='DATA <TOPIC>',task_goal='DATA GOAL',review_place_text=ReviewPlace.PED_COUNCIL.label_kz+', DATA CUSTOM',month='10',is_done=done,completion_modes=TaskCompletionMode,execution=NS(completion_mode=mode,review_result='DATA <COMMENT>') if mode else None,required_documents=[NS(id=10)],final_documents=[NS(id=82,original_file_name='DATA <FILE>.pdf',status=TaskDocumentStatus.SUBMITTED,document_type=DocumentType.REFERENCE,file_path='private/key.pdf')],success=None,warning=None,error=None)
def verify_context(lang,valid=True,code='lesson_observation'):
 result=dict(valid=valid,report_type=code,report_label='Сабақты бақылау парағы' if code=='lesson_observation' else 'Дәптер тексеру кестесі',report_id=81,document_id=82,total=0,signed_at=datetime(2026,10,24,10,30),details=[{'label':'Білім беру ұйымы','value':'DATA <SCHOOL>'},{'label':'Пән','value':'DATA SUBJECT'},{'label':'DATA CUSTOM LABEL','value':'DATA CUSTOM VALUE'}],error=None)
 return dict(request=request(lang),result=result,**result)
def render(page,data):return environment().get_template('staff/reports/'+page+'.html').render(**data)
class CompletionVerifyI18nTests(unittest.TestCase):
 def test_completion_forms_and_authored_content(self):
  for done in [False,True]:
   for mode in [None,*[e.value for e in TaskCompletionMode]]:
    parsers=[]
    for lang in ['ru','kk']:
     html=render('report_execute',context(lang,done,mode));parser=Fields();parser.feed(html);parsers.append(parser)
     for text in ['DATA &lt;TOPIC&gt;','DATA &lt;FILE&gt;.pdf','DATA CUSTOM',translate('Исполнение задачи',lang),translate(TaskCompletionMode.SIMPLE_FINAL_DOCUMENT.label_kz,lang),translate(ReviewPlace.PED_COUNCIL.label_kz,lang)]:self.assertIn(text,html)
     self.assertNotIn('private/key.pdf',html)
     if mode:self.assertIn('DATA &lt;COMMENT&gt;',html)
    self.assertEqual(parsers[0].fields,parsers[1].fields);self.assertEqual(parsers[0].links,parsers[1].links)
 def test_actual_completion_script(self):
  for lang in ['ru','kk']:
   for done in [False,True]:
    html=render('report_execute',context(lang,done));script=next(s for s in re.findall(r'<script\b[^>]*>(.*?)</script>',html,re.S) if 'function hideAll' in s)
    source='''const vm=require('vm'),ids={};for(const id of ['final-document-block','completion-action-panel','btn-upload-final','btn-done','btn-open-system-reports','reference_file'])ids[id]={style:{},required:false};
const radios=['simple_final_document','final_with_system_reports'].map(value=>({value,addEventListener(e,f){this.change=f}}));let selected=null;
vm.runInNewContext(SCRIPT,{document:{addEventListener(e,f){f()},querySelectorAll(){return radios},querySelector(){return selected},getElementById(id){return ids[id]}}});
if(ids['completion-action-panel'].style.display!=='none')throw Error('empty');selected=radios[0];selected.change();
if(DONE){if(ids['completion-action-panel'].style.display!=='none'||ids.reference_file.required)throw Error('done unlocked')}
else{if(ids['final-document-block'].style.display!=='block'||!ids.reference_file.required||ids['btn-done'].style.display!=='inline-flex'||ids['btn-open-system-reports'].style.display!=='none')throw Error('simple');selected=radios[1];selected.change();if(ids['final-document-block'].style.display!=='none'||ids.reference_file.required||ids['btn-open-system-reports'].style.display!=='inline-flex')throw Error('system')}
'''.replace('SCRIPT',json.dumps(script)).replace('DONE',str(done).lower())
    r=subprocess.run(['node','-e',source],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
 def test_public_verification_data_and_zero(self):
  for code in ['lesson_observation','checking_notebooks']:
   for lang in ['ru','kk']:
    data=verify_context(lang,code=code);before=copy.deepcopy(data['result']);html=render('verify_report',data)
    for text in [f'<html lang="{lang}">','DATA &lt;SCHOOL&gt;','DATA SUBJECT','DATA CUSTOM LABEL','DATA CUSTOM VALUE',translate(data['report_label'],lang),translate('Білім беру ұйымы',lang),'24.10.2026 10:30']:self.assertIn(text,html)
    self.assertRegex(html,r'>\s*0\s*</div>');self.assertEqual(data['result'],before);self.assertNotIn('Құжат расталды / Документ подтвержден',html)
    data['result']['report_label']='DATA <CUSTOM TITLE>';self.assertIn('DATA &lt;CUSTOM TITLE&gt;',render('verify_report',data))
 def test_invalid_expired_unknown_feedback(self):
  for lang in ['ru','kk']:
   for error,source in [('QR-код недействителен','QR-код недействителен'),('Signature has expired','Срок действия ссылки проверки истёк.'),('Signature verification failed','QR-код недействителен'),('Неизвестный тип отчета: private','Неизвестный тип отчета.'),('DB private <stack>','Не удалось проверить документ. Проверьте QR-код или ссылку.'),(None,'Не удалось проверить документ. Проверьте QR-код или ссылку.')]:
    data=verify_context(lang,False);data['error']=error;html=render('verify_report',data)
    self.assertIn(translate(source,lang),html);self.assertNotIn('private',html);self.assertNotIn('DATA SUBJECT',html);self.assertEqual(verification_message(error,lang),translate(source,lang))
 def test_completion_feedback_and_review_places(self):
  for lang in ['ru','kk']:
   source='Итоговый документ загружен. Задача завершена и отправлена на рассмотрение.';self.assertEqual(completion_message(source,lang),translate(source,lang))
   self.assertNotIn('private',completion_message('private <stack>',lang))
   text=completion_message('Не заполнены выбранные отчеты: Сабақты бақылау парағы, DATA CUSTOM',lang);self.assertIn(translate('Сабақты бақылау парағы',lang),text);self.assertIn('DATA CUSTOM',text)
   self.assertEqual(review_places_label('DATA CUSTOM',lang),'DATA CUSTOM')
   data=context(lang);data['task']=None;data['error']='Выберите файл для загрузки.';self.assertIn(translate(data['error'],lang),render('report_execute',data))
if __name__=='__main__':unittest.main()
