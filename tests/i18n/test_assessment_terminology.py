"""System labels and standard instructions; stored author data stays unchanged."""
import copy,re,unittest
from jinja2 import Environment
from test_ui_language import PROJECT,environment,request
from app.core.i18n import catalog,translate
from app.core.question_instructions import instruction_text,DEFAULTS,PAIRS,ALIASES
class AssessmentTerminologyTests(unittest.TestCase):
 def test_catalog_values_have_no_english_term(self):
  for lang in ['ru','kk']:
   for key,value in catalog(lang)._catalog.items():
    if key and isinstance(value,str):self.assertIsNone(re.search(r'\bassessment\b',value,re.I),(lang,key,value))
  self.assertEqual(translate('Assessment','ru'),'Оценивание');self.assertEqual(translate('Assessment','kk'),'Бағалау')
  self.assertEqual(translate('Добавить в Assessment','ru'),'Добавить в оценивание')
  self.assertEqual(translate('Добавить в Assessment','kk'),'Бағалау ішіне қосу')
 def test_raw_template_headings_are_localized(self):
  for f in (PROJECT/'app/web/templates').rglob('*.html'):
   for _,kind,data in Environment().lex(f.read_text()):
    if kind=='data':self.assertIsNone(re.search(r'\bAssessment\b',re.sub(r'<!--.*?-->','',data,flags=re.S)),str(f))
 def test_eleven_instructions_both_directions(self):
  self.assertEqual(len(DEFAULTS),11)
  for ru,kk in PAIRS:
   for source in [ru,kk,ru.upper(),kk.lower(),ru.replace(' ','  ')]:
    self.assertEqual(instruction_text(source,'ru'),ru);self.assertEqual(instruction_text(source,'kk'),kk)
  self.assertEqual(instruction_text('Бір дұрыс жауапты таңдаңыз','ru'),'Выберите один правильный ответ.')
  for alias,kind in ALIASES.items():self.assertEqual(instruction_text(alias,'ru'),DEFAULTS[kind])
 def test_custom_instructions_preserved_and_escaped(self):
  for value in ['Выберите два ответа и обоснуйте выбор.','Бір дұрыс жауапты таңдаңыз, шешу жолын көрсетіңіз.','<script>custom</script>','',None]:
   for lang in ['ru','kk']:self.assertEqual(instruction_text(value,lang),value or '')
  env=environment()
  for lang in ['ru','kk']:
   text=env.from_string('{{ question_instruction(value) }}').render(request=request(lang),value='<script>custom</script>')
   self.assertIn('&lt;script&gt;',text);self.assertNotIn('<script>',text)
 def test_shared_preview_uses_ui_without_mutation(self):
  from test_bilingual_questions import item
  from app.modules.assessment.enums import AssessmentLanguage
  env=environment();value=item();value.instruction='Бір дұрыс жауапты таңдаңыз';value.language=AssessmentLanguage.RUSSIAN;before=copy.deepcopy(value.__dict__)
  for lang,expected in [('ru','Выберите один правильный ответ.'),('kk','Выберите один правильный ответ.')]:
   html=env.get_template('teacher/assessment/question_bank/components/language_version.html').render(request=request(lang),bilingual_item=value)
   self.assertIn(expected,html);self.assertIn(value.text,html)
  self.assertEqual(value.__dict__,before)
