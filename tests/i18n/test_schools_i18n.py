"""Offline school directory UI; no school writes, deletions or real Excel imports."""
import ast,asyncio,copy,json,re,subprocess,unittest
from html.parser import HTMLParser
from types import SimpleNamespace as NS
from fastapi import HTTPException
from test_ui_language import environment,request,PROJECT
from app.core.i18n import translate,resolve_language
from app.core.schools_i18n import school_feedback,SCHOOL_MESSAGES
SETTLEMENT="DATA O'NEIL <Ауыл> {x}"
class Fields(HTMLParser):
 def __init__(self):super().__init__();self.fields=[];self.links=[];self.handlers=[]
 def handle_starttag(self,tag,attrs):
  d=dict(attrs)
  if tag in ['form','input','select','option','textarea','button']:self.fields.append((tag,tuple((k,v) for k,v in attrs if k not in ['class','title','placeholder','aria-label','aria-pressed','onclick'])))
  if tag=='a':self.links.append(d.get('href'))
  if 'onclick' in d:self.handlers.append(d['onclick'])
def context(lang,filled=True,editing=False):
 region=NS(id=2,name='DATA <REGION>');district=NS(id=3,name='DATA <DISTRICT>',region=region,region_id=2);school=NS(id=8,name='DATA <SCHOOL>',address='DATA <ADDRESS>',district=district,district_id=3)
 return dict(request=request(lang),user={'role':'superuser','full_name':'DATA USER'},school=school if editing else None,schools=[school] if filled else [],regions=[region],districts=[district],settlements=[SETTLEMENT],selected_region_id=2,selected_district_id=3,selected_settlement=SETTLEMENT,q='DATA <QUERY>',should_show_schools=filled,page_title='Редактировать школу' if editing else 'Добавить школу',error=None,success=None)
def render(page,data):return environment().get_template('admin/'+page+'.html').render(**data)
class SchoolsI18nTests(unittest.TestCase):
 def test_forms_filters_authored_data(self):
  for page in ['schools','school_form']:
   for filled in [False,True]:
    for editing in [False,True]:
     parsers=[]
     for lang in ['ru','kk']:
      data=context(lang,filled,editing);before=copy.deepcopy(data['school']);html=render(page,data);p=Fields();p.feed(html);parsers.append(p)
      self.assertIn('DATA &lt;REGION&gt;',html);self.assertIn('DATA &lt;DISTRICT&gt;',html)
      if page=='schools' and filled or page=='school_form' and editing:self.assertIn('DATA &lt;SCHOOL&gt;',html);self.assertIn('DATA &lt;ADDRESS&gt;',html)
      self.assertEqual(data['school'],before)
      self.assertIn(translate('Список школ' if page=='schools' else data['page_title'],lang),html)
     self.assertEqual(parsers[0].fields,parsers[1].fields);self.assertEqual(parsers[0].links,parsers[1].links)
 def test_actual_ajax_script_and_file_selection(self):
  for page in ['schools','school_form']:
   for lang in ['ru','kk']:
    html=render(page,context(lang,editing=True));script=next(s for s in re.findall(r'<script\b[^>]*>(.*?)</script>',html,re.S) if 'async function loadDistricts' in s)
    r=subprocess.run(['node',str(PROJECT/'tests/i18n/schools_dom.js')],input=json.dumps(dict(script=script,page=page,settlement=SETTLEMENT)),capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr);data=json.loads(r.stdout)
    self.assertIn('/api/orgs/districts?region_id=2',data['requests']);self.assertIn('<option value="">'+translate('Ошибка загрузки',lang)+'</option>',data['changes']);self.assertIn('<option value="">'+translate('Выберите район',lang)+'</option>',data['changes'])
    if page=='schools':self.assertIn(translate('Файл не выбран',lang),data['changes']);self.assertEqual(data['confirms'],[translate('Удалить эту школу?',lang)]*2)
 def test_error_headers_and_terminology_fix_preserved(self):
  for lang in ['ru','kk']:
   for source in SCHOOL_MESSAGES:self.assertEqual(school_feedback(source,lang),translate(source,lang))
   text=school_feedback('В Excel-файле нет колонки: Ұйым атауы',lang);self.assertIn('Ұйым атауы',text);self.assertNotIn('private',school_feedback('private <stack>',lang))
   data=context(lang);data['error']='В Excel-файле нет колонки: DATA <COLUMN>';self.assertIn('DATA &lt;COLUMN&gt;',render('schools',data))
   for key in ['МІБ жоспары','ВШК жоспары','План МІБ','План ВШК']:self.assertEqual(translate(key,lang),'План ВШК' if lang=='ru' else 'МІБ жоспары')
 def test_bulk_delete_confirmation(self):
  for lang in ['ru','kk']:
   p=Fields();p.feed(render('schools',context(lang)));self.assertEqual(len(p.handlers),1)
   js='let seen;const fn=new Function("confirm",'+json.dumps(p.handlers[0])+');for(const v of [false,true]){if(fn(s=>{seen=s;return v})!==v)throw Error("confirmation bypass")}process.stdout.write(seen);'
   r=subprocess.run(['node','-e',js],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout,translate('Удалить выбранные школы?',lang))
 def test_import_early_validation_localized(self):
  path=PROJECT/'app/routers/web/org/org_import.py';tree=ast.parse(path.read_text());fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef));fn.decorator_list=[];fn.returns=None
  for a in fn.args.args:a.annotation=None
  fn.args.defaults=[ast.Constant(None) for _ in fn.args.defaults];module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
  for lang in ['ru','kk']:
   for name,source in [('', 'Файл не выбран'),('data.csv','Разрешен только .xlsx файл')]:
    scope=dict(HTTPException=HTTPException,school_feedback=school_feedback,resolve_language=resolve_language);exec(compile(module,str(path),'exec'),scope)
    with self.assertRaises(HTTPException) as caught:asyncio.run(scope['import_schools_xlsx'](request(lang),file=NS(filename=name),_user=NS(ui_language=lang)))
    self.assertEqual(caught.exception.status_code,400);self.assertEqual(caught.exception.detail,translate(source,lang))
if __name__=='__main__':unittest.main()
