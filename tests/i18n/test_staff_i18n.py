"""Personnel localization preserves canonical position, role and context values."""
import asyncio,json,re,subprocess
from types import SimpleNamespace as NS
import pytest
from starlette.exceptions import HTTPException
from test_ui_language import environment,request,PROJECT
from test_education_i18n import Fields
from app.modules.planning.enums import ResponsibleRole
from app.core.staff_i18n import staff_message,staff_http_exception_handler,staff_validation_response
from app.core.i18n import translate


def context(lang,filled=True):
 names=set()
 for f in (PROJECT/'app/web/templates/staff/members').glob('*.html'):names.update(re.findall(r'm\.(\w+)',f.read_text()))
 values=dict.fromkeys(names,None)
 values.update(id=7,full_name='DATA <b>NAME</b>',iin='000000000007',position_text='кітапханашы',subject='DATA SUBJECT',
  university='DATA UNIVERSITY',qualification_category='DATA CATEGORY',is_active=filled,
  roles=[NS(role=ResponsibleRole.LIBRARIAN,role_context='DATA CONTEXT',is_active=filled)],
  total_experience_years=12,ped_experience_years=5)
 member=NS(**values)
 return dict(request=request(lang),user={'role':'school_admin','full_name':'USER DATA'},m=member,
  members=[member] if filled else [],allowed_positions=['кітапханашы','директор'],error=None,success=None,
  responsible_roles=[{'value':r.value,'label_kz':r.label_kz} for r in ResponsibleRole],
  member_roles=[{'role':'librarian','context':'DATA CONTEXT'}] if filled else [],
  import_report=NS(created=2,updated=3,skipped=1,errors=['DATA SOURCE ERROR']) if filled else None)

@pytest.mark.parametrize('page',['school_staff','member_edit','member_roles'])
@pytest.mark.parametrize('filled',[True,False])
def test_staff_rendering_and_form_values(page,filled):
 texts=[]
 for lang in ('ru','kk'):
  text=environment().get_template('staff/members/'+page+'.html').render(**context(lang,filled))
  assert f'<html lang="{lang}">' in text
  assert 'DATA <b>NAME</b>' not in text
  texts.append(text)
 fields=[]
 for text in texts:
  parser=Fields();parser.feed(text)
  fields.append([(tag,tuple((k,v) for k,v in attrs if k!='data-confirm')) for tag,attrs in parser.fields])
 assert fields[0]==fields[1]
 if page!='member_roles':
  assert 'value="кітапханашы"' in texts[0]
  assert 'библиотекарь' in texts[0]
  assert 'кітапханашы' in texts[1]
 if page=='member_roles':
  assert 'DATA CONTEXT' in texts[0] or not filled
  for text,expected in zip(texts,['Библиотекарь','Кітапханашы']):
   options=json.loads(re.search(r'const ROLES = (.*?);',text)[1])
   assert next(r['label_kz'] for r in options if r['value']=='librarian')==expected

@pytest.mark.parametrize('lang',['ru','kk'])
def test_flash_counts_and_errors(lang):
 req=request(lang);req.scope['path']='/staff/school'
 from urllib.parse import urlencode
 req.scope['query_string']=urlencode({'success':'Сотрудник добавлен'}).encode()
 text=environment().get_template('staff/members/school_staff.html').render(**dict(context(lang,False),request=req))
 assert translate('Сотрудник добавлен',lang) in text
 message=staff_message(req,'Импорт: создано 2, обновлено 3, пропущено 4, ошибок 1')
 assert all(x in message for x in ['2','3','4','1'])
 assert ('жаңартылды' if lang=='kk' else 'обновлено') in message
 for code in [400,403,404,422]:
  response=asyncio.run(staff_http_exception_handler(req,HTTPException(code,'Сотрудник не найден',headers={'X-Test':'kept'})))
  assert response.status_code==code and response.headers['X-Test']=='kept'
  assert json.loads(response.body)['detail']==translate('Сотрудник не найден',lang)
 response=staff_validation_response(req,[{'loc':['body','file'],'type':'missing','input':'PRIVATE DATA'}])
 assert response.status_code==422 and 'PRIVATE DATA' not in response.body.decode()
 assert staff_message(req,'Некорректное число: PRIVATE DATA')==translate('Проверьте числовые значения.',lang)

def test_staff_scope_does_not_intercept_other_routes():
 req=request('ru');req.scope['path']='/unrelated'
 response=asyncio.run(staff_http_exception_handler(req,HTTPException(418,'UNCHANGED')))
 assert response.status_code==418 and json.loads(response.body)['detail']=='UNCHANGED'

@pytest.mark.parametrize('lang',['ru','kk'])
def test_role_editor_builds_unchanged_payload_and_escapes_context(lang):
 text=environment().get_template('staff/members/member_roles.html').render(**context(lang))
 scripts=re.findall(r'<script\b[^>]*>(.*?)</script>',text,re.S)
 script=next(s for s in scripts if 'function roleRowHtml' in s)
 messages=environment().from_string('{{ ui_messages()|tojson }}').render(request=request(lang))
 source='const messages='+messages+''';
const vm=require('vm'); const inputs=[];
const rows=ROWS;
const doc={addEventListener(){},createElement(){return {}},getElementById(){return {innerHTML:'',appendChild(x){inputs.push(x)}}},querySelectorAll(){return rows.map(x=>({querySelector(q){return {value:q==='.rr-role'?x.role:x.context}}}))}};
const sandbox={document:doc,window:{SchoolMonitorI18n:{t(k,values={}){return messages[k].replace(/\\{(p\\d+)\\}/g,(m,n)=>values[n]??m)}}}};
vm.createContext(sandbox);
vm.runInContext(SCRIPT,sandbox);
sandbox.buildHidden();
process.stdout.write(JSON.stringify({html:sandbox.roleRowHtml(0,'librarian',rows[0].context),inputs}));
'''.replace('SCRIPT',json.dumps(script)).replace('ROWS',json.dumps([{'role':'librarian','context':'DATA \"<>&\' CONTEXT'},{'role':'','context':'SKIP'}]))
 result=subprocess.run(['node','-e',source],capture_output=True,text=True)
 assert result.returncode==0,result.stderr
 data=json.loads(result.stdout)
 assert [(i['name'],i['value']) for i in data['inputs']]==[('roles[0].role','librarian'),('roles[0].context','DATA "<>&\' CONTEXT')]
 parser=Fields();parser.feed(data['html'])
 inp=next(dict(attrs) for tag,attrs in parser.fields if tag=='input')
 assert inp['value']=='DATA "<>&\' CONTEXT'
 assert ('Жою' if lang=='kk' else 'Удалить') in data['html']

def test_static_staff_script_runs_and_toggles_other_position():
 script=(PROJECT/'app/web/static/js/school_staff.js').read_text()
 assert '{%' not in script and '{{' not in script
 source='''let update;const select={value:'__other__',addEventListener(e,f){update=f}},other={style:{}};
const document={addEventListener(e,f){f()},getElementById(id){return id==='positionSelect'?select:other}};
'''+script+'''
if(other.style.display!=='block'||!other.required)throw Error('other');
select.value='кітапханашы';update();
if(other.style.display!=='none'||other.required)throw Error('standard');
'''
 result=subprocess.run(['node','-e',source],capture_output=True,text=True)
 assert result.returncode==0,result.stderr
