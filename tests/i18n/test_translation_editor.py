"""Readable editor projection and real JS -> protected server save contract."""
import copy,json,subprocess,unittest
from types import SimpleNamespace as NS
from test_ui_language import PROJECT,environment,request
from test_bilingual_segment_spacing import composition
from test_bilingual_ai_generation import parse,req
from app.modules.assessment.helpers.bilingual_question_contract import source_payload,translation_fields,get_value,make_variant,assert_variant_contract
from app.modules.assessment.helpers.translation_editor import build_translation_editor

def example():
 response=parse(json.dumps(composition()),req());source=source_payload(response.questions[0]);source['text_segments']=list(source['text_segments']);target=response.metadata['bilingual_payload'];kind=response.questions[0].question_type
 values={f'f{i}':get_value(target,path) for i,(path,_) in enumerate(translation_fields(source,kind))}
 return source,target,kind,values
class TranslationEditorTests(unittest.TestCase):
 def test_statement_is_one_group_without_plain_duplicate(self):
  source,target,kind,values=example();groups=build_translation_editor(source,kind,values)
  statements=[g for g in groups if g['label']=='Условие задания'];self.assertEqual(len(statements),1)
  group=statements[0];self.assertEqual(group['kind'],'rich');self.assertEqual(len(group['target_segments']),7)
  self.assertEqual([s['text'] for s in group['target_segments'] if s['type']=='latex'],[s['text'] for s in source['text_segments'] if s['type']=='latex'])
  self.assertTrue(group['statement_field']);self.assertEqual(group['target_segments'][0]['text'],'Даны функции ')
  self.assertTrue(any(g['label']=='Вариант ответа' and g['detail']=='A' for g in groups))
 def test_all_editor_fields_are_reachable_across_types(self):
  from test_bilingual_questions import item,Type,translations
  for kind in Type:
   source=source_payload(item(kind));values=translations(source,kind);groups=build_translation_editor(source,kind,values);reachable=set()
   for group in groups:
    if group['kind']=='text':reachable.add(group['name'])
    else:
     reachable.update(s['field'] for s in group['target_segments'] if 'field' in s)
     if group['statement_field']:reachable.add(group['statement_field'])
   self.assertEqual(reachable,set(values),kind)
 def test_image_alt_and_math_only_options_are_not_lost(self):
  source,target,kind,values=example();source['content']['options'][0]['segments']=[dict(type='latex',text='x^2')]
  source['text_segments'].append(dict(type='image',object_key='protected',alt='Изображение'))
  fields=translation_fields(source,kind);values={f'f{i}':text for i,(_,text) in enumerate(fields)}
  groups=build_translation_editor(source,kind,values)
  self.assertTrue(any(g['label']=='Описание изображения' for g in groups))
  option=next(g for g in groups if g['label']=='Вариант ответа' and g['detail']=='A')
  self.assertEqual(option['target_segments'][0]['type'],'latex')
 def test_template_collapses_saved_editor_and_opens_pending(self):
  source,target,kind,values=example();groups=build_translation_editor(source,kind,values)
  rows=[dict(name=k,value=v) for k,v in values.items()]
  for language in ['ru','kk']:
   args=dict(request=request(language),item=NS(id=7),rows=rows,editor_groups=groups,source_hash='hash',target_language='ru',readonly=False,saved=True,stale=False,error=None,pending=False)
   env=environment();html=env.get_template('teacher/assessment/question_bank/components/translation_editor.html').render(**args)
   self.assertNotIn('Фрагмент',html);self.assertNotIn('data-translation-editor method="get"',html);self.assertNotIn('Перевести с помощью AI',html)
   self.assertNotIn('<details class="qb-translation-panel" open',html);self.assertIn('contenteditable="plaintext-only"',html);self.assertIn('data-statement-token="f(x)=2x+1"',html)
   self.assertIn('name="source_hash"',html)
   args.update(pending=True,saved=False)
   html=env.get_template('teacher/assessment/question_bank/components/translation_editor.html').render(**args)
   self.assertIn('<details class="qb-translation-panel" open',html)
 def test_real_js_synchronizes_whole_statement_and_server_accepts(self):
  source,target,kind,values=example();groups=build_translation_editor(source,kind,values);statement=next(g for g in groups if g['label']=='Условие задания')
  input_data=dict(values=values,statement=statement,edit='Даны следующие функции ')
  code=r'''
const fs=require('fs'),vm=require('vm');const data=JSON.parse(fs.readFileSync(0,'utf8'));
const hidden=Object.entries(data.values).map(([name,value])=>({name,value}));
const fields=data.statement.target_segments.filter(s=>s.field).map(s=>({tagName:'SPAN',dataset:{translationField:s.field},innerText:s.text,addEventListener(n,f){this.listener=f;}}));
const children=data.statement.target_segments.map(s=>s.field?fields.find(f=>f.dataset.translationField===s.field):{dataset:{statementToken:s.text}});
const statement={dataset:{statementField:data.statement.statement_field},children};const save={disabled:true};let submit;
const form={querySelectorAll(selector){if(selector.includes('input['))return hidden;if(selector==='[data-translation-field]')return fields;if(selector==='[data-statement-field]')return [statement];throw Error(selector);},querySelector(){return save;},addEventListener(n,f){submit=f;}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{document:{querySelector:()=>form}});
fields[0].innerText=data.edit;fields[0].listener();submit();
if(save.disabled)throw Error('save not enabled');process.stdout.write(JSON.stringify(Object.fromEntries(hidden.map(h=>[h.name,h.value]))));
'''
  result=subprocess.run(['node','-e',code,str(PROJECT/'app/web/static/js/teacher/assessment/question_bank/translation_editor.js')],input=json.dumps(input_data),capture_output=True,text=True,timeout=10)
  self.assertEqual(result.returncode,0,result.stderr);posted=json.loads(result.stdout)
  payload=make_variant(source,kind,posted);assert_variant_contract(source,payload,kind)
  self.assertTrue(payload['text'].startswith('Даны следующие функции f(x)=2x+1'))
  self.assertEqual(payload['text_segments'][0]['text'],'Даны следующие функции ')
  self.assertEqual(payload['answer_key'],target['answer_key'])
