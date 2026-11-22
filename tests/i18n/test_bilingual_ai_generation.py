"""One-call RU/KZ generation, protected contracts, atomic persistence and tracks."""
import ast,asyncio,copy,json,unittest
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import patch
from test_ui_language import PROJECT,environment,request
# Initializes pure validators without unrelated production configuration/storage.
from test_bilingual_questions import extract_function
from app.modules.assessment.ai.question_prompt_builder import AIQuestionPromptBuilder
from app.modules.assessment.ai.question_response_parser import AIQuestionResponseParser
from app.modules.assessment.ai.exceptions import AIProviderError
from app.modules.assessment.schemas.ai_question_generator_dto import *
from app.modules.assessment.enums import AssessmentLanguage as Lang,AssessmentQuestionType as Type,AssessmentQuestionDifficulty as Difficulty
from app.modules.assessment.helpers.bilingual_question_contract import source_payload,assert_variant_contract,target_language
from app.modules.assessment.helpers.ai_education_track import selected_track,validate_objective_track
from app.modules.assessment.services.assessment_question_validation_service import AssessmentQuestionValidationService as Validator
from app.modules.assessment.services import generated_bilingual_service as persistence

def load(filename,scope):
 tree=ast.parse((PROJECT/filename).read_text());tree.body=[n for n in tree.body if not isinstance(n,(ast.Import,ast.ImportFrom))]
 exec(compile('from __future__ import annotations\n'+ast.unparse(tree),filename,'exec'),scope)
 return scope
class SDKError(Exception):pass
scope=dict(AIQuestionPromptBuilder=AIQuestionPromptBuilder,AIQuestionResponseParser=AIQuestionResponseParser,AIProviderError=AIProviderError,
 get_settings=lambda:None,AsyncOpenAI=None,**{n:SDKError for n in ['APIConnectionError','APIStatusError','APITimeoutError','AuthenticationError','RateLimitError']})
Base=load('app/modules/assessment/ai/openai_question_provider.py',scope)['OpenAIQuestionProvider']
scope2=dict(OpenAIQuestionProvider=Base,json=json,deepcopy=copy.deepcopy,replace=replace,AIQuestionPromptBuilder=AIQuestionPromptBuilder,
 AIQuestionResponseParser=AIQuestionResponseParser,AssessmentLanguage=Lang,source_payload=source_payload,assert_variant_contract=assert_variant_contract,target_language=target_language,Validator=Validator)
module=load('app/modules/assessment/ai/bilingual_generation_provider.py',scope2);Provider=module['BilingualGenerationProvider'];parse=module['parse_bilingual']
def req(lang=Lang.KAZAKH):
 return AIQuestionGenerationRequestDTO(None,2,'Алгебра',10,lang,'Жиындар',1,Decimal(1),
  (AIQuestionGenerationObjectiveDTO(8,'10.1.1','Жиындар',1,Decimal(1)),),
  (AIQuestionGenerationTypeDTO(Type.SINGLE_CHOICE,1,Decimal(1)),),AIQuestionGenerationDifficultyDTO(0,100,0))
def raw_pair(lang='kk'):
 source=dict(question_type='single_choice',title='Жиындар',text='2 элементі A жиынына жата ма?',
 text_segments=[dict(type='text',text='2 элементі A жиынына жата ма?'),dict(type='latex',text=r'2\in A')],
 instruction='Бір дұрыс жауапты таңдаңыз',content={'options':[{'value':'A','segments':[{'type':'text','text':'Иә'}]},{'value':'B','segments':[{'type':'text','text':'Жоқ'}]}]},
 answer_key={'value':'A'},grading_settings={},difficulty='medium',max_score=1,learning_objective_ids=[8],explanation='Дұрыс жауап')
 other=copy.deepcopy(source);other.update(title='Множества',text='Принадлежит ли 2 множеству A?',instruction='Выберите один правильный ответ',explanation='Верный ответ')
 other['text_segments'][0]['text']=other['text'];other['content']['options'][0]['segments'][0]['text']='Да';other['content']['options'][1]['segments'][0]['text']='Нет'
 if lang=='ru':source,other=other,source
 return dict(questions=[source],translation=dict(language='ru' if lang=='kk' else 'kk',questions=[other]))
class DB:
 def __init__(self):self.rows=[];self.flushes=0
 async def refresh(self,*a,**kw):pass
 async def get(self,*a):return None
 def add(self,v):self.rows.append(v)
 async def flush(self):self.flushes+=1
class BilingualAIGenerationTests(unittest.TestCase):
 def test_one_api_request_for_both_languages(self):
  for lang in [Lang.KAZAKH,Lang.RUSSIAN]:
   calls=[]
   async def create(**kw):
    calls.append(kw);return NS(status='completed',output=[],output_text=json.dumps(raw_pair(lang.value)))
   client=NS(responses=NS(create=create));provider=Provider(client=client,settings=NS(openai_api_key='test',openai_model='test',OPENAI_TIMEOUT_SECONDS=60))
   response=asyncio.run(provider.generate_questions(req(lang)))
   self.assertEqual(len(calls),1);self.assertFalse(calls[0]['store']);self.assertIn('translation',calls[0]['instructions']);self.assertIn('JSON',calls[0]['input'])
   self.assertEqual(len(response.questions),1);self.assertEqual(response.metadata['bilingual_language'],target_language(lang))
   self.assertEqual(response.metadata['bilingual_payload']['answer_key'],response.questions[0].answer_key)
 def test_missing_or_inconsistent_translation_is_rejected(self):
  for mutation in ['missing','language','answer','number','formula','score','difficulty','objectives','structure']:
   raw=raw_pair();other=raw['translation']['questions'][0]
   if mutation=='missing':raw.pop('translation')
   if mutation=='language':raw['translation']['language']='kk'
   if mutation=='answer':other['answer_key']['value']='B'
   if mutation=='number':other['text_segments'][0]['text']='Принадлежит ли 3 множеству A?'
   if mutation=='formula':other['text_segments'][1]['text']=r'3\in A'
   if mutation=='score':other['max_score']=2
   if mutation=='difficulty':other['difficulty']='basic'
   if mutation=='objectives':other['learning_objective_ids']=[]
   if mutation=='structure':other['content']['options'].reverse()
   with self.subTest(mutation=mutation),self.assertRaises(ValueError):parse(json.dumps(raw),req())
 def test_both_payloads_saved_together_without_commit(self):
  response=parse(json.dumps(raw_pair()),req());question=response.questions[0]
  item=NS(**module['question_payload'](question));item.__dict__.update(id=7,subject_id=2,grade_level=10,quarter=1,
   question_type=question.question_type,difficulty=question.difficulty,max_score=question.max_score,language=Lang.KAZAKH,status='draft',created_by_user_id=3,objectives=[NS(learning_objective_id=8)])
  async def get(*args,**kw):return item
  with patch.object(persistence.QuestionBankRepo,'get_aggregate_by_id',get),patch.object(persistence,'QuestionBankLanguageVariant',lambda **kw:NS(**kw)):
   db=DB();asyncio.run(persistence.save_generated_variant(db,item_id=7,response=response,user_id=3,language=Lang.KAZAKH))
   self.assertEqual(len(db.rows),1);self.assertEqual(db.rows[0].language,'ru');self.assertTrue(item.requires_bilingual);self.assertEqual(db.rows[0].source_fingerprint,persistence.fingerprint(item))
   bad=replace(response,metadata={});empty=DB()
   with self.assertRaises(ValueError):asyncio.run(persistence.save_generated_variant(empty,item_id=7,response=bad,user_id=3,language=Lang.KAZAKH))
   self.assertEqual(empty.rows,[])
 def test_track_contract_and_wrong_objective(self):
  self.assertEqual(selected_track(10,'emn'),'emn');self.assertEqual(selected_track(11,'general'),'');self.assertIsNone(selected_track(9,None))
  for grade,track in [(10,None),(11,''),(9,'ogn'),(10,'invalid')]:
   with self.assertRaises(ValueError):selected_track(grade,track)
  for track in ['general','emn','ogn']:validate_objective_track('',10,track)
  validate_objective_track('emn',10,'emn')
  with self.assertRaises(ValueError):validate_objective_track('ogn',10,'emn')
  with self.assertRaises(ValueError):validate_objective_track('emn',10,'general')
 def test_ui_has_track_and_primary_language_independent_of_interface(self):
  env=environment();scope=NS(subject_id=2,grade_level=10,subject_name_kz='Алгебра',subject_name_ru='Алгебра');objective=NS(learning_objective_id=8,code='10.1',quarter=1,title_kz='Мақсат',title_ru='Цель',title_segments_kz=(),title_segments_ru=())
  for ui in ['ru','kk']:
   html=env.get_template('teacher/assessment/question_bank/ai_create.html').render(request=request(ui),user=NS(full_name='Teacher',role='teacher'),teaching_scope=[scope],objectives=[objective],scope='2:10',subject_id=2,grade_level=10,quarter=1,token='test',values={},selected_language='kk',education_track='emn',track_pending=False,question_types=[Type.SINGLE_CHOICE],difficulties=list(Difficulty),languages=list(Lang))
   self.assertIn('name="education_track" value="emn"',html);self.assertIn('value="emn" selected',html);self.assertIn('value="ogn"',html);self.assertIn('data-qb-objective-language-value value="kk"',html)
 def test_persistence_hook_is_before_completion_and_commit(self):
  source=(PROJECT/'app/modules/assessment/services/teacher_ai_question_web_service.py').read_text()
  self.assertLess(source.index('await save_generated_variant'),source.index('await Repo.complete'))
  self.assertLess(source.index('await Repo.complete'),source.index('await db.commit()',source.index('await Repo.complete')))
  self.assertEqual(source.count('await provider.generate_questions(request)'),1)
 def test_track_filter_is_applied_in_repository(self):
  from app.modules.assessment.repositories.teacher_question_bank_repo import TeacherQuestionBankRepo
  from app.modules.assessment.repositories.learning_objective_formulation_repo import LearningObjectiveFormulationRepo
  statements=[]
  class QueryDB:
   async def execute(self,stmt):
    statements.append(str(stmt.whereclause.compile(compile_kwargs={'literal_binds':True})))
    return NS(all=lambda:[])
  async def forms(*args,**kw):return {}
  with patch.object(LearningObjectiveFormulationRepo,'for_objectives',forms):
   asyncio.run(TeacherQuestionBankRepo.list_learning_objectives(QueryDB(),subject_id=2,grade_level=10,quarter=1,education_track='emn'))
  self.assertIn("education_track IN ('', 'emn')",statements[0]);self.assertNotIn("'ogn'",statements[0])
 def test_failure_of_second_version_rolls_back_generation_transaction(self):
  # Run the actual orchestrator body with in-memory boundaries; no real API/DB.
  from datetime import datetime,timezone
  row=dict(status='pending',fingerprint=None,created_at=datetime.now(timezone.utc),token='a'*32,item_id=None)
  events=[]
  class Session:
   async def __aenter__(self):return self
   async def __aexit__(self,*a):pass
   async def commit(self):events.append('commit')
   async def rollback(self):events.append('rollback')
  class Repo:
   @staticmethod
   async def get(*a,**kw):return row
   @staticmethod
   async def claim(*a,**kw):row.update(status='running',fingerprint=kw['fingerprint'])
   @staticmethod
   async def complete(*a,**kw):events.append('complete');row['status']='completed'
   @staticmethod
   async def fail(*a,**kw):events.append('fail');row['status']='failed'
  async def build(*a,**kw):return req()
  async def generate(*a):events.append('api');return parse(json.dumps(raw_pair()),req())
  async def save(*a,**kw):events.append('save_source');return NS(item_ids=(7,),warnings=())
  async def quarter(*a,**kw):pass
  async def save_second(*a,**kw):events.append('save_translation');raise ValueError('translation failed')
  async def status(**kw):return row
  scope=dict(Repo=Repo,Single=NS(build_request=build),Generator=NS(save_generated_questions_in_transaction=save),LearningObjectiveTableImportRepo=NS(assign_item_quarter=quarter),save_generated_variant=save_second,validate_token=lambda x:None,fingerprint=lambda x:'digest',datetime=datetime,timezone=timezone,timedelta=__import__('datetime').timedelta,AIRequestNotFound=ValueError,asyncio=asyncio,logger=NS(exception=lambda *a,**kw:None))
  fn=extract_function('app/modules/assessment/services/teacher_ai_question_web_service.py','generate',scope)
  result=asyncio.run(fn(NS(status=status),session_factory=Session,provider=NS(generate_questions=generate),token='a'*32,user_id=3,staff_member_id=4,data=NS(difficulty=Difficulty.MEDIUM,quarter=1,language=Lang.KAZAKH)))
  self.assertEqual(result['status'],'failed');self.assertEqual(events,['commit','api','save_source','save_translation','rollback','fail','commit']);self.assertNotIn('complete',events)
 def test_translation_survives_real_source_item_normalization(self):
  from app.modules.assessment.services import ai_question_generator_service as generator
  response=parse(json.dumps(raw_pair()),req())
  with patch.object(generator,'QuestionBankItem',lambda **kw:NS(**kw)):
   built=generator.AIQuestionGeneratorService._build_bank_item(request=req(),question=response.questions[0],created_by_user_id=3)
  assert_variant_contract(source_payload(built),response.metadata['bilingual_payload'],built.question_type)
