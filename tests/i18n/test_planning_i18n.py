"""Planning UI localization preserves text, selectors and archive form behavior."""
import asyncio,json
from types import SimpleNamespace as NS
import pytest
from starlette.exceptions import HTTPException
from test_ui_language import environment,request
from test_education_i18n import Fields
from app.modules.planning.enums import ResponsibleRole,ReviewPlace,PlanPeriodType,PlanStatus
from app.modules.reports.enums import DocumentType
from app.modules.planning.schemas.school_plan_row11_schemas import SchoolPlanRow11EditPageDTO,SchoolPlanRow11OptionDTO
from app.core.planning_period import MONTH_NAMES_KZ
from app.core.planning_i18n import planning_http_exception_handler,planning_validation_response
from app.core.i18n import translate

PAGES=['school_dashboard','plan_view','plan_preview','direction_edit','row11_edit']
def context(lang,status='draft',filled=True):
 plan=NS(id=5,academic_year='2026–2027',status=PlanStatus(status),template_id=3,template=NS(id=3,name='DATA TEMPLATE'))
 direction=NS(id=2,short_title='DATA DIRECTION',full_title='DATA FULL DIRECTION')
 row=NS(id=9,is_custom=True,topic='DATA <b>TOPIC</b>',goal='DATA GOAL',control_object='DATA OBJECT',control_type='DATA TYPE',methods='DATA METHODS',deadlines='DATA DEADLINE',second_control='DATA SECOND',risk_text='DATA RISK',decision_text='DATA DECISION',period_type=PlanPeriodType.MONTHS,period_values='9,10',period_value_int=None,role_assignments=[NS(role=ResponsibleRole.LIBRARIAN)],responsibles='DATA RESPONSIBLE SAMPLE',responsibles_text='DATA RESPONSIBLE',review_place='DATA REVIEW SAMPLE',review_places_text='DATA REVIEW',management_decision='DATA DOCUMENT SAMPLE',documents_text='DATA DOCUMENT')
 page=SchoolPlanRow11EditPageDTO(plan_id=5,academic_year=plan.academic_year,direction_id=2,direction_name=direction.full_title,row_id=9,row_order=1,topic=row.topic,goal=row.goal,control_object=row.control_object,control_type=row.control_type,methods=row.methods,deadlines=row.deadlines,second_control=row.second_control,period_type='months',month=10,period_values='9,10',selected_months=[9,10],is_archived=status=='archived',responsible_roles=[SchoolPlanRow11OptionDTO('librarian','Кітапханашы',True)],review_places=[SchoolPlanRow11OptionDTO('ped_council','Пед.кеңес',True)],required_documents=[SchoolPlanRow11OptionDTO('report','Есеп',True)])
 return dict(request=request(lang),user={'role':'school_admin','full_name':'USER DATA'},school=NS(name='DATA SCHOOL'),academic_year=plan.academic_year,error=None,tab='my',plans=[plan] if filled else [],active_plan=plan if filled else None,templates_active=[plan.template] if filled else [],plan=plan,page=page,template_directions=[NS(direction_id=2,direction=direction)] if filled else [],direction=direction,direction_id=2,rows4=[row] if filled else [],rows11=[row] if filled else [],directions=[NS(direction=direction,rows4=[row],rows11=[row])] if filled else [],MONTH_NAMES=MONTH_NAMES_KZ,ROLE_LABELS={'librarian':'Кітапханашы'},row_months_selected={9:[9,10]},row_required_docs_map={9:['report']},row_review_places_map={9:['ped_council']},document_types=list(DocumentType),review_places=list(ReviewPlace),meta=NS(school_name='DATA SCHOOL',director_fio='DATA DIRECTOR'))

@pytest.mark.parametrize('page',PAGES)
@pytest.mark.parametrize('status',['draft','active','archived'])
@pytest.mark.parametrize('filled',[True,False])
def test_planning_pages_and_form_contract(page,status,filled):
 texts=[]
 for lang in ('ru','kk'):
  text=environment().get_template('planning/school/'+page+'.html').render(**context(lang,status,filled))
  assert f'<html lang="{lang}">' in text
  assert 'DATA <b>TOPIC</b>' not in text
  texts.append(text)
 fields=[]
 for text in texts:
  parser=Fields();parser.feed(text)
  fields.append([(tag,tuple((k,v) for k,v in attrs if k!='data-confirm')) for tag,attrs in parser.fields])
 assert fields[0]==fields[1]
 assert texts[0]!=texts[1]
 if page=='row11_edit':
  for text in texts:
   assert 'value="9,10"' in text and 'value="librarian"' in text and 'value="ped_council"' in text
   assert 'DATA GOAL' in text and 'DATA METHODS' in text
  assert 'Октябрь' in texts[0] and 'Қазан' in texts[1]
 if page=='school_dashboard' and filled:
  if status=='archived':assert all('class="planning-archive-form"' not in t for t in texts)
  else:assert all('class="planning-archive-form"' in t and plan_year in t for t,plan_year in [(texts[0],'2026–2027'),(texts[1],'2026–2027')])
 if filled and page in ('plan_preview','direction_edit'):
  assert all('DATA GOAL' in t and 'DATA SECOND' in t for t in texts)

@pytest.mark.parametrize('lang',['ru','kk'])
@pytest.mark.parametrize('kind',['month','months','monthly','quarter','all_year'])
def test_structured_period_is_localized_without_mutating_row(lang,kind):
 row=NS(period_type=PlanPeriodType(kind),period_value_int=10,period_values='9,10',deadlines='DATA LEGACY')
 before=vars(row).copy()
 result=environment().from_string('{{ row|planning_period }}').render(request=request(lang),row=row)
 assert vars(row)==before
 expected={'month':('Месяц: Октябрь','Ай: Қазан'),'months':('Месяцы: Сентябрь, Октябрь','Айлар: Қыркүйек, Қазан'),'monthly':('Ежемесячно','Ай сайын'),'quarter':('Ежеквартально','Тоқсан сайын'),'all_year':('В течение года','Жыл бойы')}
 assert result==expected[kind][lang=='kk']

@pytest.mark.parametrize('lang',['ru','kk'])
def test_period_free_text_and_http_errors(lang):
 env=environment()
 for row in [NS(period_text='DATA READY',period_type='month'),NS(period_type=None,deadlines='DATA LEGACY')]:
  result=env.from_string('{{ row|planning_period }}').render(request=request(lang),row=row)
  assert result in ('DATA READY','DATA LEGACY')
 req=request(lang);req.scope['path']='/planning/school/5'
 response=asyncio.run(planning_http_exception_handler(req,HTTPException(403,'Нельзя удалить строку из шаблона',headers={'X-Test':'keep'})))
 assert response.status_code==403 and response.headers['X-Test']=='keep'
 assert json.loads(response.body)['detail']==translate('Нельзя удалить строку из шаблона',lang)
 response=planning_validation_response(req,[{'loc':['body','month'],'type':'invalid','input':'PRIVATE DATA'}])
 assert response.status_code==422 and 'PRIVATE DATA' not in response.body.decode()
 req.scope['path']='/unrelated'
 response=asyncio.run(planning_http_exception_handler(req,HTTPException(418,'UNCHANGED')))
 assert response.status_code==418 and json.loads(response.body)['detail']=='UNCHANGED'

@pytest.mark.parametrize('lang',['ru','kk'])
def test_row_deletion_confirmation_keeps_selection_and_url(lang):
 import subprocess
 from test_ui_language import PROJECT
 script=(PROJECT/'app/web/static/js/row_select.js').read_text()
 messages=environment().from_string('{{ ui_messages()|tojson }}').render(request=request(lang))
 source='const messages='+messages+''';
const vm=require('vm'),listeners={},buttons={},forms={};let confirmed='',allow=false;
for(const kind of ['row4','row11']){
 buttons['btnDelete-'+kind]={dataset:{},addEventListener(e,f){this.click=f}};
 forms['deleteForm-'+kind]={submissions:0,submit(){this.submissions++}};
}
const doc={addEventListener(e,f){if(e==='DOMContentLoaded')f();else listeners[e]=f},
 querySelectorAll(){return []},getElementById(id){return buttons[id]||forms[id]||(id==='pageRoot'?{dataset:{planId:'5',directionId:'2'}}:null)}};
const sandbox={document:doc,console:{log(){}},confirm(text){confirmed=text;return allow},window:{SchoolMonitorI18n:{t(k){return messages[k]}}}};
vm.createContext(sandbox);vm.runInContext(SCRIPT,sandbox);
const row={dataset:{kind:'row11',rowId:'9',isCustom:'0'},classList:{add(){}}};
const click=()=>listeners.click({target:{closest(){return {closest(){return row}}}}});
click();if(!buttons['btnDelete-row11'].disabled)throw Error('template row must stay protected');
row.dataset.isCustom='1';click();if(buttons['btnDelete-row11'].disabled)throw Error('custom row should be selectable');
buttons['btnDelete-row11'].click();if(forms['deleteForm-row11'].submissions!==0)throw Error('cancelled');
allow=true;buttons['btnDelete-row11'].click();
process.stdout.write(JSON.stringify({form:forms['deleteForm-row11'],confirmed}));
'''.replace('SCRIPT',json.dumps(script))
 result=subprocess.run(['node','-e',source],capture_output=True,text=True)
 assert result.returncode==0,result.stderr
 data=json.loads(result.stdout)
 assert data['form']['action']=='/planning/school/5/direction/2/rows11/9/delete'
 assert data['form']['submissions']==1
 assert data['confirmed']==translate('Удалить выбранную строку?',lang)
