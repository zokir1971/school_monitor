"""Education forms preserve values and bilingual content when UI locale changes."""
import json
from html.parser import HTMLParser
from types import SimpleNamespace as NS
import pytest
from test_ui_language import environment, request
from app.core.i18n import translate
from app.core.education_ui_messages import EDUCATION_WEB_MESSAGES

PAGES=['education/'+x+'.html' for x in ['nobd_import','curriculum_reference','teaching_load','class_curriculum']]+['super/education/subjects/'+x+'.html' for x in ['form','delete','categories','list']]+['super/assessment/learning_objective_'+x+'.html' for x in ['upload_choice','import','reference_edit','reference_list','formulations','table_import','reference_delete']]
class Fields(HTMLParser):
 def __init__(self):super().__init__();self.fields=[]
 def handle_starttag(self,tag,attrs):
  if tag in ('form','input','select','option','button','textarea'):self.fields.append((tag,tuple((k,v) for k,v in attrs if k not in ('placeholder','title','aria-label','class','aria-pressed'))))
def context(locale,filled):
 subject=NS(id=10,code='math',name_kz='Математика KZ',name_ru='Математика RU',is_active=True,category_id=1,sort_order=10,curriculum_role='general')
 row=dict(id=81,version=3,code='5.1.1.1',subject_name='DATA subject',grade_level=5,quarters=[1,2],education_track=None,program_title='DATA program',program_id=2,title_kz='DATA KZ',title_ru='DATA RU',is_active=True,title_segments_kz=[{'type':'text','text':'DATA KZ'}],title_segments_ru=[{'type':'text','text':'DATA RU'}])
 page=NS(filters=NS(subject_id=None,grade=None,quarter=None,track='',state='all',query=''),rows=[NS(**row)] if filled else [],total=int(filled),page=1,pages=1,academic_year_label='2026–2027',items=[],subjects=[],teachers=[],classes=[],academic_year_start=2026)
 return dict(request=request(locale),user={'role':'superuser','full_name':'USER DATA'},school_name='SCHOOL DATA',year=2026,csrf='TOKEN DATA',error=None,notice=None,subjects=[subject] if filled else [],categories=[],profiles=[],rules=[],rule_errors={},subject_by_id={},category_by_id={},policy_labels={'general':'Без специальных языковых ограничений'},rule_languages={'kz':'Қазақша','ru':'Русский'},languages={'kz':'Қазақша','ru':'Русский'},roles={},teachers=[],blocks=[],classes=[],class_blocks=[],form={},editing=False,policies={'general':'Без специальных языковых ограничений'},page=page,row=NS(**row),values=row,rows=[row] if filled else [],sources=[],settings={},selected_pages={},payload=None,draft_id='DRAFT',preview=None,delete_preview=NS(subject=subject,blockers=[],fingerprint='FINGERPRINT'),scope={},result=None,deleted=None,counters=None,preview_token=None,saved=False,stage='upload',stats={},summary={},filters={},school_classes=[],academic_year_start=2026)
@pytest.mark.parametrize('page',PAGES)
@pytest.mark.parametrize('filled',[False,True])
def test_pages(page,filled):
 texts=[]
 for locale in ('ru','kk'):
  data=context(locale,filled)
  if page.endswith('subjects/delete.html'):data['preview']=data['delete_preview']
  if page.endswith(('learning_objective_import.html','learning_objective_table_import.html')):
   if filled:data['payload']=dict(metadata=dict(program_title_kz='DATA program',order_number='467',order_date='2026-10-23',appendix_number='1',grade_from=5,grade_to=5),table_binding={'subject_name':'DATA subject'},rows=data['rows'],warnings=[])
   else:data.pop('payload')
  text=environment().get_template(page).render(**data);assert f'<html lang="{locale}">' in text;texts.append(text)
 assert texts[0]!=texts[1]
 fields=[]
 for text in texts:
  parser=Fields();parser.feed(text);fields.append(parser.fields)
 assert fields[0]==fields[1]
 if page.endswith('reference_edit.html'):
  assert all('DATA KZ' in t and 'DATA RU' in t and 'DATA program' in t for t in texts)
 if page.endswith('subjects/delete.html'):assert all('pattern="УДАЛИТЬ"' in t for t in texts)
def test_js_dictionary_and_policy():
 env=environment()
 for lang in ('ru','kk'):
  values=json.loads(env.from_string('{{ ui_messages()|tojson }}').render(request=request(lang)))
  for key,source in EDUCATION_WEB_MESSAGES.items():assert values[key]==translate(source,lang)
 labels=env.from_string('{{ education_labels(labels)|tojson }}').render(request=request('kk'),labels={'general':'Без специальных языковых ограничений'})
 assert json.loads(labels)=={'general':'Арнайы тілдік шектеулерсіз'}

@pytest.mark.parametrize('locale',['ru','kk'])
def test_nobd_preview_preserves_confirmation_and_student_choices(locale):
 data=context(locale,True)
 data.update(preview_token='PREVIEW TOKEN',preview=NS(rows=[{'iin':'DATA'}],skipped=0,
  organizations=['DATA ORGANIZATION'],errors=[],groups=[NS(grade=10,letter='A',count=20,
  languages=['русский'],inferred_language='ru',saved_language='ru',key='10_A',existing=True,saved_track='emn')]))
 text=environment().get_template('education/nobd_import.html').render(**data)
 for value in ['name="language_10_A"','value="ru" selected','name="track_10_A"','value="emn" selected',
               'name="confirm_school"','name="confirm_tracks"','name="confirm_languages"','PREVIEW TOKEN','DATA ORGANIZATION']:
  assert value in text
 assert ('ЕМН' if locale=='ru' else 'ЖМБ') in text

@pytest.mark.parametrize('locale',['ru','kk'])
def test_goal_delete_preview_keeps_security_fields(locale):
 data=context(locale,True);subject=data['subjects'][0]
 data.update(scope=dict(subject_id=10,grade=5,instruction_language='ru'),preview=NS(subject=subject,
    languages={'ru':'Русский','kz':'Қазақша'},language_label='Русский',count=2,blockers=[],fingerprint='EXACT FINGERPRINT'))
 text=environment().get_template('super/assessment/learning_objective_reference_delete.html').render(**data)
 for value in ['pattern="УДАЛИТЬ"','EXACT FINGERPRINT','name="csrf" value="TOKEN DATA"','name="instruction_language" value="ru"']:
  assert value in text

def test_catalog_semantics():
 assert translate('Сохранить / Сақтау','ru')=='Сохранить'
 assert translate('Сохранить / Сақтау','kk')=='Сақтау'
 assert translate('ЕМН / ЖМБ','ru')=='ЕМН'
 assert translate('ЕМН / ЖМБ','kk')=='ЖМБ'
 assert translate('XLS / XLSX жүктеу','ru')=='Загрузка XLS / XLSX'
