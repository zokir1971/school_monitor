"""PDF HTML and generation contract tests; no database writes or real signatures."""
import ast,asyncio,copy,re,unittest
from datetime import datetime
from types import SimpleNamespace as NS
from html.parser import HTMLParser
from jinja2 import Environment,FileSystemLoader,select_autoescape
from test_ui_language import request,PROJECT,environment
from test_report_forms_i18n import context as form_context,PAGES as FORMS
from app.core.i18n import translate
from app.core.report_pdf_i18n import select_document_language,saved_report_language,report_pdf_context,DOCUMENT_LANGUAGE_ERROR
from app.modules.reports.system_schemas.lesson_observation_schema import LESSON_OBSERVATION_SCHEMA
from app.modules.reports.system_schemas.checking_notebooks_schemas import CHECKING_NOTEBOOKS_SYSTEM_SCHEMA
PAGES=['lesson_observation','checking_notebooks']
class Cells(HTMLParser):
 def __init__(self):super().__init__();self.cell=None;self.values=[];self.qr=[];self.language=None
 def handle_starttag(self,tag,attrs):
  d=dict(attrs)
  if tag=='td':self.cell=[]
  if tag=='img':self.qr.append(d.get('src'))
  if tag=='html':self.language=d.get('lang')
 def handle_data(self,data):
  if self.cell is not None:self.cell.append(data)
 def handle_endtag(self,tag):
  if tag=='td' and self.cell is not None:self.values.append(' '.join(' '.join(self.cell).split()));self.cell=None

def fixture(page,language='ru',custom=False):
 schema=copy.deepcopy(LESSON_OBSERVATION_SCHEMA if page==PAGES[0] else CHECKING_NOTEBOOKS_SYSTEM_SCHEMA)
 if custom:
  schema={'sections':[{'title':'DATA <CUSTOM SECTION>','criteria':[{'key':'c1','text':'DATA <CUSTOM CRITERION>'}]}],'criteria':[{'key':'c1','label_kz':'DATA <CUSTOM CRITERION>'}],'score_scale':[0,1,2,3]}
 names=set(re.findall(r'report\.(\w+)',(PROJECT/'app/web/templates/staff/reports/user_templates'/f'{page}_pdf.html').read_text()));report=NS(**dict.fromkeys(names,'DATA <AUTHORED>'));report.id=81;report.total=0;report.total_score=0;report.max_score=16;report.percent=0;report.level='Төмен';report.lesson_datetime=datetime(2026,10,24,10,30);report.submitted_at=datetime(2026,10,24,11,30);report.feedback='';report.suggestion_control='';report.conclusion='DATA <CONCLUSION>';report.recommendations='DATA <RECOMMENDATIONS>'
 scores={'c1':0,'score_c1':0}
 for section in schema.get('sections',[]):
  for criterion in section.get('criteria',[]):scores[criterion.get('key','')]=0
  for sub in section.get('subsections',[]):
   for criterion in sub.get('criteria',[]):scores[criterion.get('key','')]=0
 for criterion in schema.get('criteria',[]):
  if isinstance(criterion,dict):scores[criterion.get('key','')]=0
 report.criteria_scores={'document_language':language,'scores':scores,'info':{'feedback':'DATA <FEEDBACK>','suggestion_control':'DATA <SUGGESTION>'},'total_score':0,'max_score':16,'percent':0,'level':'Төмен'}
 document=NS(template_mode='custom' if custom else 'standard',custom_template_id=8 if custom else None)
 return report,schema,document

def pdf_environment():return Environment(loader=FileSystemLoader(str(PROJECT/'app/web/templates')),autoescape=select_autoescape(['html']))
def render(page,language,custom=False,ui='kk'):
 report,schema,document=fixture(page,language,custom);before=copy.deepcopy((report.criteria_scores,schema));context=report_pdf_context(request(ui),report,document)
 html=pdf_environment().get_template(f'staff/reports/user_templates/{page}_pdf.html').render(request=request(ui),report=report,schema=schema,qr_file='data:image/png;base64,DATA_QR',**context)
 assert (report.criteria_scores,schema)==before
 return html,report,schema,document

class ReportPdfI18nTests(unittest.TestCase):
 def test_saved_language_independent_of_interface(self):
  for language in ['ru','kk']:
   report,_,document=fixture(PAGES[0],language);ctx=report_pdf_context(request('kk' if language=='ru' else 'ru'),report,document);self.assertEqual(ctx['pdf_language'],language);self.assertEqual(saved_report_language(report),language)
   self.assertEqual(select_document_language(None,language,'kk'),language)
  self.assertEqual(select_document_language('kz'),'kk');self.assertEqual(select_document_language(None,None,'kk'),'kk')
  for value in ['en','wrong']:
   with self.assertRaises(ValueError) as caught:select_document_language(value)
   self.assertEqual(str(caught.exception),DOCUMENT_LANGUAGE_ERROR)
 def test_language_selector_defaults_saved_and_signed(self):
  for page in FORMS:
   for ui in ['ru','kk']:
    for saved in [None,'ru','kk']:
     for signed in [False,True]:
      data=form_context(ui,page,signed);data['report'].criteria_scores={} if saved is None else {'document_language':saved};html=environment().get_template('staff/reports/user_templates/'+page).render(**data)
      if signed and saved is None:
       self.assertNotIn('id="document-language"',html);self.assertIn(translate('Язык ранее подписанного PDF не сохранён; файл открывается в исходном виде.',ui),html);continue
      control=re.search(r'<select id="document-language"(.*?)</select>',html,re.S).group(0);self.assertIn('disabled',control) if signed else self.assertNotIn('disabled',control)
      selected=re.search(r'<option value="(ru|kk)"\s*selected',control).group(1);self.assertEqual(selected,saved or ui)
 def test_pdf_titles_scores_zero_and_qr(self):
  for page in PAGES:
   parsed=[]
   for lang in ['ru','kk']:
    html,report,schema,document=render(page,lang);p=Cells();p.feed(html);parsed.append(p);self.assertEqual(p.language,lang);self.assertEqual(p.qr,['data:image/png;base64,DATA_QR']);self.assertIn('DATA &lt;AUTHORED&gt;',html)
    self.assertIn('0',p.values);self.assertIn(translate('Сабақты бақылау парағы' if page==PAGES[0] else 'Дәптер тексеруді бағалау парағы',lang),html)
    if page==PAGES[1]:self.assertIn('0%',html);self.assertIn('Низкий уровень' if lang=='ru' else translate('Низкий уровень','kk'),html)
    else:self.assertIn('DATA &lt;FEEDBACK&gt;',html)
   numeric=lambda p:[v for v in p.values if re.fullmatch(r'\d+(?:%|: \d+)?',v)]
   self.assertEqual(numeric(parsed[0]),numeric(parsed[1]))
 def test_custom_content_and_standard_labels(self):
  for page in PAGES:
   for lang in ['ru','kk']:
    html,_,_,_=render(page,lang,True);self.assertIn('DATA &lt;CUSTOM CRITERION&gt;',html)
    if page==PAGES[0]:self.assertIn('DATA &lt;CUSTOM SECTION&gt;',html)
  report,_,doc=fixture(PAGES[1]);ctx=report_pdf_context(request('ru'),report,doc);self.assertEqual(ctx['pdf_schema_text']('Дәптерлердің толық болуы'),'Наличие полного комплекта тетрадей')
  doc.template_mode=None;ctx=report_pdf_context(request('ru'),report,doc);self.assertEqual(ctx['pdf_schema_text']('Дәптерлердің толық болуы'),'Наличие полного комплекта тетрадей')
  doc.template_mode='custom';ctx=report_pdf_context(request('ru'),report,doc);self.assertEqual(ctx['pdf_schema_text']('Дәптерлердің толық болуы'),'Дәптерлердің толық болуы')
 def test_real_generator_rendering_and_browser_cleanup(self):
  for page,filename in [(PAGES[0],'lesson_observation_service.py'),(PAGES[1],'checking_notebooks_service.py')]:
   path=PROJECT/'app/modules/reports/services'/filename;source=path.read_text();compile(source,str(path),'exec');tree=ast.parse(source);fn=copy.deepcopy(next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=='_generate_signed_pdf'));fn.decorator_list=[];fn.returns=None
   for arg in fn.args.kwonlyargs:arg.annotation=None
   module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
   for fail in [False,True]:
    captured={}
    class Page:
     async def set_content(self,html,**kw):captured['html']=html;captured['wait']=kw
     async def pdf(self,**kw):
      captured['pdf']=kw
      if fail:raise RuntimeError('render failed')
      return b'MOCK_PDF'
    class Browser:
     async def new_page(self):return Page()
     async def close(self):captured['closed']=True
    class Manager:
     async def __aenter__(self):return NS(chromium=self)
     async def __aexit__(self,*args):return False
     async def launch(self,**kw):return Browser()
    scope=dict(async_playwright=Manager,report_pdf_context=report_pdf_context);exec(compile(module,str(path),'exec'),scope);report,schema,doc=fixture(page,'ru')
    coroutine=scope['_generate_signed_pdf'](request=request('kk'),templates=pdf_environment(),report=report,schema=schema,qr_data_uri='DATA_QR',document=doc)
    if fail:
     with self.assertRaises(RuntimeError):asyncio.run(coroutine)
    else:self.assertEqual(asyncio.run(coroutine),b'MOCK_PDF')
    self.assertTrue(captured['closed']);self.assertIn('<html lang="ru">',captured['html']);self.assertEqual(captured['pdf']['format'],'A4');self.assertEqual(set(captured['pdf']['margin'].values()),{'15mm'})
 def test_metadata_write_and_signed_guard_order(self):
  for file in ['lesson_observation_service.py','checking_notebooks_service.py']:
   source=(PROJECT/'app/modules/reports/services'/file).read_text();guard=source.index('Отчет уже подписан. Редактирование запрещено.');language=source.index('document_language = select_document_language(',guard);self.assertGreater(language,guard)
   self.assertIn('"document_language": document_language',source);self.assertIn('**report_pdf_context(request, report, document)',source)
   # Signature and download route implementations remain outside this patch's changes.
if __name__=='__main__':unittest.main()
