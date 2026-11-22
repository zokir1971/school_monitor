"""Expert registry UI changes must not change assignment and authorization form values."""
import asyncio,json
from types import SimpleNamespace as NS
from datetime import datetime
import pytest
from starlette.exceptions import HTTPException
from test_ui_language import environment,request
from test_education_i18n import Fields
from app.core.assessment_i18n import application_http_exception_handler,assessment_error_message
from app.core.i18n import translate

PAGES=['list','create','edit','detail','policy']
def context(locale,filled,can_edit=True):
 expert=NS(expert_id=7,iin='000000000007',full_name='<b>EXPERT DATA</b>',school_id=19,
  school_name='SCHOOL DATA',district_id=2,district_name='DISTRICT DATA',region_id=1,region_name='REGION DATA',
  subject_id=10,subject_name='SUBJECT DATA',specialty_id=3,specialty_name='CUSTOM RU',specialty_name_kz='CUSTOM KZ',
  phone='+77000000000',email='test@example.test',position_text='POSITION DATA',education_text='Жоғары',
  specialty_text='SPECIALTY DATA',qualification_category_text='педагог-сарапшы',ped_experience_years=12,
  user_id=9,has_account=filled,is_active=filled,created_at=datetime(2026,10,23),updated_at=None,deactivated_at=None)
 specialty=NS(id=3,name='CUSTOM RU',name_ru='CUSTOM RU',name_kz='CUSTOM KZ',is_active=filled,code='custom')
 subject=NS(id=10,subject_id=10,name='SUBJECT DATA',name_ru='SUBJECT RU',name_kz='SUBJECT KZ')
 school=NS(school_id=19,school_name='SCHOOL DATA',district_id=2,district_name='DISTRICT DATA')
 return dict(request=request(locale),user={'role':'superuser','full_name':'USER DATA'},expert=expert,
  page=NS(experts=[expert] if filled else [],districts=[NS(district_id=2,district_name='DISTRICT DATA')],subjects=[subject]),
  options=NS(schools=[school],subjects=[subject],specialties=[specialty]),form=expert,error='ЖСН 12 цифрдан тұруы тиіс.',
  district_id=None,subject_id=None,status='',can_edit=can_edit,csrf_token='TOKEN DATA',specialties=[specialty],subjects=[subject],
  rules=[NS(id=4,specialty_id=3,subject_id=10,grade_from=5,grade_to=6,instruction_language='ru',is_active=filled)] if filled else [],
  languages={'all':'Все языки обучения','ru':'Русский','kz':'Казахский'},specialty_names={3:'CUSTOM RU'},subject_names={10:'SUBJECT RU'})

@pytest.mark.parametrize('page',PAGES)
@pytest.mark.parametrize('filled',[False,True])
@pytest.mark.parametrize('can_edit',[False,True])
def test_expert_pages_and_form_contract(page,filled,can_edit):
 texts=[]
 for lang in ('ru','kk'):
  text=environment().get_template('region/assessment/question_bank_experts/'+page+'.html').render(**context(lang,filled,can_edit))
  assert f'<html lang="{lang}">' in text
  assert '<b>EXPERT DATA</b>' not in text
  texts.append(text)
 fields=[]
 for text in texts:
  parser=Fields();parser.feed(text)
  # This read-only field is display-only. The submitted education_text value remains canonical.
  fields.append([(tag,attrs) for tag,attrs in parser.fields if dict(attrs).get('id')!='education_text_display'])
 assert fields[0]==fields[1]
 assert texts[0]!=texts[1]
 if page in ('create','edit'):
  assert all('value="Жоғары"' in t for t in texts)
  assert 'CUSTOM RU' in texts[0] and 'CUSTOM KZ' in texts[1]
 if page=='policy':
  if can_edit:
   assert all('name="name_ru" value="CUSTOM RU"' in t and 'name="name_kz" value="CUSTOM KZ"' in t for t in texts)
  else:assert 'CUSTOM KZ' in texts[1]

def test_localized_expert_errors_keep_status_and_headers():
 for locale in ('ru','kk'):
  req=request(locale);req.scope['path']='/region/assessment/question-bank/experts/policy'
  response=asyncio.run(application_http_exception_handler(req,HTTPException(403,'Обновите страницу перед сохранением.',headers={'X-Test':'kept'})))
  assert response.status_code==403 and response.headers['X-Test']=='kept'
  assert json.loads(response.body)['detail']==translate('Обновите страницу перед сохранением.',locale)
  assert assessment_error_message(req,'Сарапшы табылмады.',404)==('Эксперт не найден.' if locale=='ru' else 'Сарапшы табылмады.')

def test_user_text_and_missing_specialty_translation_fallback():
 env=environment()
 for lang in ('ru','kk'):
  for value in ['CUSTOM DATA','<script>DATA</script>']:
   result=env.from_string('{{ expert_standard_label(value) }}').render(request=request(lang),value=value)
   assert result==value.replace('<','&lt;').replace('>','&gt;')
  result=env.from_string('{{ expert_specialty_name(obj) }}').render(request=request(lang),obj={'specialty_name':'CUSTOM RU'})
  assert result=='CUSTOM RU'

def test_specialty_option_projection_supplies_both_names():
 # Compile only the option query method, avoiding application startup and any real database.
 import ast
 from pathlib import Path
 from sqlalchemy import select
 from sqlalchemy.dialects import postgresql
 from sqlalchemy import table,column
 source=Path('app/modules/assessment/services/question_bank_expert_service.py').read_text()
 tree=ast.parse(source)
 cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='QuestionBankExpertService')
 method=next(n for n in cls.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='specialty_options')
 method.decorator_list=[]
 model=NS(id=column('id'),name_ru=column('name_ru'),name_kz=column('name_kz'),is_active=column('is_active'))
 namespace={'select':select,'QuestionBankExpertSpecialty':model}
 exec(compile(ast.Module(body=[method],type_ignores=[]),'<specialty_options>','exec'),namespace)
 class DB:
  async def execute(self,stmt):
   sql=str(stmt.compile(dialect=postgresql.dialect()))
   assert 'name_ru' in sql and 'name_kz' in sql and 'is_active IS true' in sql
   return [NS(id=3,name_ru='CUSTOM RU',name_kz='CUSTOM KZ')]
 result=asyncio.run(namespace['specialty_options'](DB()))
 assert result==[{'id':3,'name':'CUSTOM RU','name_ru':'CUSTOM RU','name_kz':'CUSTOM KZ'}]

def test_display_fields_are_optional_on_existing_dtos():
 from dataclasses import fields
 from app.modules.assessment.schemas.question_bank_expert_schemas import QuestionBankExpertListItemDTO
 definition={f.name:f for f in fields(QuestionBankExpertListItemDTO)}
 assert definition['specialty_name_kz'].default is None
 assert definition['specialty_name'].default=='Требуется настройка'
