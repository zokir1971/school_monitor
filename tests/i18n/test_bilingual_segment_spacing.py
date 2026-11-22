"""Regression: meaningful spaces beside math must survive bilingual validation."""
import asyncio,copy,json,unittest
from types import SimpleNamespace as NS
from test_bilingual_ai_generation import raw_pair,req,parse,Provider,Lang
from app.modules.assessment.helpers.bilingual_question_contract import assert_variant_contract,source_payload,translation_fields,make_variant

def composition(language='kk'):
 raw=raw_pair();a=raw['questions'][0];b=raw['translation']['questions'][0]
 def segments(texts):return [dict(type='latex' if i in [1,3,5] else 'text',text=s) for i,s in enumerate(texts)]
 a['text_segments']=segments(['Мына ',r'f(x)=2x+1',' және ',r'g(x)=x^2-3',' функциялары берілген. Күрделі ',r'f(g(x))',' функциясын анықтаңыз.'])
 b['text_segments']=segments(['Даны функции ',r'f(x)=2x+1',' и ',r'g(x)=x^2-3','. Найдите сложную функцию ',r'f(g(x))','.'])
 if language=='ru':raw=dict(questions=[b],translation=dict(language='kk',questions=[a]))
 return raw
class BilingualSegmentSpacingTests(unittest.TestCase):
 def test_composition_in_both_directions_preserves_spaces(self):
  for language in [Lang.KAZAKH,Lang.RUSSIAN]:
   response=parse(json.dumps(composition(language.value)),req(language));target=response.metadata['bilingual_payload']
   expected='Даны функции ' if language==Lang.KAZAKH else 'Мына '
   self.assertEqual(target['text_segments'][0]['text'],expected)
   self.assertEqual(len(target['text_segments']),7)
   source=source_payload(response.questions[0]);source['text_segments']=list(source['text_segments'])
   assert_variant_contract(source,target,response.questions[0].question_type)
 def test_multisegment_generation_still_calls_api_once(self):
  calls=[]
  async def create(**kw):calls.append(kw);return NS(status='completed',output=[],output_text=json.dumps(composition()))
  provider=Provider(client=NS(responses=NS(create=create)),settings=NS(openai_api_key='test',openai_model='test',OPENAI_TIMEOUT_SECONDS=60))
  response=asyncio.run(provider.generate_questions(req()))
  self.assertEqual(len(calls),1);self.assertEqual(response.metadata['bilingual_language'],'ru')
 def test_answer_and_formula_protection_stays_strict(self):
  response=parse(json.dumps(composition()),req());source=source_payload(response.questions[0]);source['text_segments']=list(source['text_segments']);target=response.metadata['bilingual_payload']
  for kind in ['answer','formula','structure']:
   bad=copy.deepcopy(target)
   if kind=='answer':bad['answer_key']['value']='B'
   if kind=='formula':bad['text_segments'][1]['text']='f(x)=3x+1'
   if kind=='structure':bad['content']['options'].append(copy.deepcopy(bad['content']['options'][0]))
   with self.assertRaises(ValueError):assert_variant_contract(source,bad,response.questions[0].question_type)
  bad=copy.deepcopy(target);bad['answer_key']['value']='B'
  with self.assertRaisesRegex(ValueError,r'Поле: \$\.answer_key\.value'):assert_variant_contract(source,bad,response.questions[0].question_type)
 def test_option_segment_boundaries_keep_spaces(self):
  response=parse(json.dumps(composition()),req());source=source_payload(response.questions[0]);source['text_segments']=list(source['text_segments'])
  source['content']['options'][0]['segments']=[dict(type='text',text='Жауап: '),dict(type='latex',text='x^2'),dict(type='text',text=' болады.')]
  fields=translation_fields(source,response.questions[0].question_type)
  values={f'f{i}':('Ответ: ' if text=='Жауап: ' else ' будет.' if text==' болады.' else text) for i,(_,text) in enumerate(fields)}
  result=make_variant(source,response.questions[0].question_type,values)
  self.assertEqual(result['content']['options'][0]['segments'][0]['text'],'Ответ: ')
  self.assertEqual(result['content']['options'][0]['segments'][2]['text'],' будет.')
