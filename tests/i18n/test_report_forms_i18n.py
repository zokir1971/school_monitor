"""Report fill localization preserves snapshots, score fields and canonical level."""
import copy,json,re,subprocess,unittest
from datetime import datetime
from types import SimpleNamespace as NS
from html.parser import HTMLParser
from test_ui_language import environment,request,PROJECT
from app.modules.reports.system_schemas.lesson_observation_schema import LESSON_OBSERVATION_SCHEMA
from app.modules.reports.system_schemas.checking_notebooks_schemas import CHECKING_NOTEBOOKS_SYSTEM_SCHEMA
from app.core.i18n import translate
PAGES=['fill_lesson_observation.html','checking_notebooks_fill.html']
class Fields(HTMLParser):
 def __init__(self):super().__init__();self.fields=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if a.get('id')=='level_display':return
  if tag in ['form','input','textarea','button','select','option']:self.fields.append((tag,tuple((k,v) for k,v in attrs if k not in ['aria-label','title','placeholder','data-confirm','class','aria-pressed'])))

def context(lang,page,signed=False,custom=False):
 names=set()
 for name in PAGES:names.update(re.findall(r'report\.(\w+)',(PROJECT/'app/web/templates/staff/reports/user_templates'/name).read_text()))
 report=NS(**dict.fromkeys(names,'DATA VALUE'));report.id=5;report.staff_member_id=14;report.submitted_at=datetime(2026,10,24) if signed else None;report.rows_json={};report.criteria_scores={"document_language":"ru"}
 schema=copy.deepcopy(LESSON_OBSERVATION_SCHEMA if page==PAGES[0] else CHECKING_NOTEBOOKS_SYSTEM_SCHEMA)
 document=NS(report_label='Сабақты бақылау парағы' if page==PAGES[0] else 'Проверка тетрадей',schema_json=schema,template_mode='custom' if custom else 'standard',custom_template_id=8 if custom else None)
 return dict(request=request(lang),user={'role':'school_staff','full_name':'DATA USER'},month_item_id=9,selected_report_id=21,template_id=8 if custom else None,document=document,report=report,schema=schema,saved_info={'teacher_full_name':'DATA <b>NAME</b>','feedback':'DATA FEEDBACK','suggestion_control':'DATA SUGGESTION','check_date':'2026-10-24T10:30'},scores={'criterion_0':2},score_scale=schema.get('score_scale'),criteria=schema.get('criteria',[]),total_score=2,max_score=16,percent=13,level='Төмен',error=None)

class ReportFormsI18nTests(unittest.TestCase):
 def test_pages_payload_and_readonly_contract(self):
  for page in PAGES:
   for signed in [False,True]:
    for custom in [False,True]:
     with self.subTest(page=page,signed=signed,custom=custom):
      texts=[]
      for lang in ['ru','kk']:
       data=context(lang,page,signed,custom);before=copy.deepcopy(data['schema'])
       text=environment().get_template('staff/reports/user_templates/'+page).render(**data)
       self.assertEqual(data['schema'],before);self.assertEqual(data['document'].schema_json,before);self.assertNotIn('DATA <b>NAME</b>',text);texts.append(text)
      parsed=[]
      for text in texts:
       p=Fields();p.feed(text);parsed.append(p.fields)
      self.assertEqual(parsed[0],parsed[1])
      if signed:
       for text in texts:self.assertNotIn('value="complete"',text);self.assertIn('disabled',text)
      else:self.assertIn('value="complete"',texts[0]);self.assertIn('value="complete"',texts[1])
      if page==PAGES[1]:
       self.assertIn('name="info_level"',texts[0]);self.assertIn('value="Төмен"',texts[0])
       for text in texts:self.assertIn('value="Дәптерлердің толық болуы"',text)
       if custom:self.assertIn('<strong>Дәптерлердің толық болуы</strong>',texts[0])
       else:self.assertIn('<strong>Наличие полного комплекта тетрадей</strong>',texts[0]);self.assertIn('<strong>Дәптерлердің толық болуы</strong>',texts[1])
      else:
       self.assertIn('DATA FEEDBACK',texts[0]);self.assertIn('DATA FEEDBACK',texts[1])
       self.assertIn('Жоспарлау' if custom else 'Планирование',texts[0])

 def test_custom_snapshot_metadata_and_unknown_labels(self):
  env=environment()
  caption='Дәптерлердің толық болуы'
  for lang in ['ru','kk']:
   for key in ['template_id','document']:
    data={'request':request(lang),'value':caption,'template_id':None,'document':None}
    data[key]=8 if key=='template_id' else NS(custom_template_id=8,template_mode='custom')
    result=env.from_string('{{ report_form_label(value) }}').render(**data)
    self.assertEqual(result,caption)
   self.assertEqual(env.from_string('{{ report_form_label(value) }}').render(request=request(lang),value='DATA <NAME>'),'DATA &lt;NAME&gt;')
   snapshot=NS(schema_json={'criteria':[{'key':'criterion_0','label_kz':caption}]},custom_template_id=None,template_mode='standard')
   result=env.from_string('{{ report_form_label(value) }}').render(request=request(lang),value=caption,document=snapshot,template_id=8)
   self.assertEqual(result,'Наличие полного комплекта тетрадей' if lang=='ru' else caption)

 def test_score_scripts_keep_totals_and_canonical_level(self):
  for page in PAGES:
   for lang in ['ru','kk']:
    text=environment().get_template('staff/reports/user_templates/'+page).render(**context(lang,page))
    script=next(s for s in re.findall(r'<script\b[^>]*>(.*?)</script>',text,re.S) if 'function updateTotal' in s)
    messages=environment().from_string('{{ ui_messages()|tojson }}').render(request=request(lang))
    for total in [0,59,60,84,85,100]:
     with self.subTest(page=page,lang=lang,total=total):
      source='const messages='+messages+';const total='+str(total)+''';const vm=require('vm');
const checked=Array.from({length:Math.floor(total/2)},()=>({value:'2'}));if(total%2)checked.push({value:'1'});
const inputs={total_score:{value:0},max_score:{value:100},percent:{value:0},level:{value:'—'},level_display:{value:''}};
const radios=checked.length?checked:[{value:'0'}];radios.forEach(r=>r.addEventListener=()=>{});
const doc={getElementById(id){return inputs[id]},querySelectorAll(q){return q.includes(':checked')?radios:radios}};
vm.runInNewContext(SCRIPT,{document:doc,window:{SchoolMonitorI18n:{t(k){return messages[k]??k}}}});
process.stdout.write(JSON.stringify(inputs));
'''.replace('SCRIPT',json.dumps(script))
      result=subprocess.run(['node','-e',source],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr);values=json.loads(result.stdout)
      self.assertEqual(values['total_score']['value'],total)
      if page==PAGES[1]:
       level='Жоғары' if total>=85 else 'Орта' if total>=60 else 'Төмен' if total>0 else '—'
       self.assertEqual(values['percent']['value'],total);self.assertEqual(values['level']['value'],level)
       label='Высокий уровень' if total>=85 else 'Средний уровень' if total>=60 else 'Низкий уровень' if total>0 else None
       self.assertEqual(values['level_display']['value'],translate(label,lang) if label else '—')

 def test_no_javascript_preserves_saved_level_display(self):
  for lang in ['ru','kk']:
   text=environment().get_template('staff/reports/user_templates/'+PAGES[1]).render(**context(lang,PAGES[1]))
   self.assertIn('id="level_display" value="'+translate('Низкий уровень',lang)+'"',text)
   self.assertRegex(text,r'id="level"\s+name="info_level"\s+value="Төмен"')
if __name__=='__main__':unittest.main()
