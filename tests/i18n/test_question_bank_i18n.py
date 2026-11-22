"""UI language must never modify the persisted Question Contract."""
import asyncio
from copy import deepcopy
from datetime import datetime
from html import unescape
import json
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace as NS

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.question_bank_i18n import (question_bank_http_exception_handler,
    question_bank_validation_response, is_question_bank_request)
from app.core.question_bank_ui_messages import QB_WEB_MESSAGES
from app.core.i18n import translate
from app.modules.assessment.enums import (AssessmentQuestionType,AssessmentQuestionDifficulty,
    AssessmentLanguage,QuestionBankItemStatus,QuestionBankItemOrigin)
from test_ui_language import environment,request,PROJECT


def question(kind):
    text='Авторский текст: Дұрыс жауап, Оқу мақсаттары — сохранить без перевода <x>.'
    segments=[{'type':'text','text':text}]
    opts=[{'value':'A','segments':[{'type':'text','text':'Авторский вариант A'}]},
          {'value':'B','segments':[{'type':'latex','text':r'x\\in A'}]}]
    content={'options':opts};answer={'value':'A'};grading={}
    if kind=='multiple_choice':answer={'values':['A']}
    if kind=='true_false':content={'statements':[{'id':'S1','segments':segments}]};answer={'statements':{'S1':True}}
    if kind=='short_text':content={};answer={'accepted_answers':['Дұрыс жауап','Авторский ответ']}
    if kind=='number':content={'parts':[{'id':'N1','segments':segments}]};answer={'parts':{'N1':{'value':2,'tolerance':0,'unit':'кг'}}}
    if kind=='matching':content={'left':opts,'right':opts};answer={'pairs':[{'left':'A','right':'B'},{'left':'B','right':'A'}]};grading={'matching_score_policy':'per_pair_v1'}
    if kind=='ordering':content={'items':opts};answer={'order':['B','A']};grading={'ordering_score_policy':'per_position_v1'}
    if kind=='fill_gaps':content={'input_mode':'text_input','segments':[{'type':'text','text':'Авторский пропуск '},{'type':'gap','id':'G1'}]};answer={'gaps':{'G1':{'accepted_answers':['Авторский ответ']}}}
    if kind=='fill_gaps':grading={'fill_gaps_score_policy':'per_gap_v1'}
    if kind=='formula':content={'parts':[{'id':'F1','segments':segments,'variables':['x'],'meaning_options':[{'value':'V1','label':'Авторская величина'}]}]};answer={'parts':{'F1':{'expression':r'x\\cap A','variable_meanings':{'x':'V1'}}}}
    if kind=='formula':grading={'formula_score_policy':'per_part_v1'}
    if kind=='manual_review':content={};answer={};grading={'manual_review':True,'criteria':[{'id':'C1','title':'Авторский критерий','description':'Авторский дескриптор','max_score':1}]}
    if kind=='image_choice':content={'options':[dict(x,object_key='question-bank/test.png',alt='Авторская картинка') for x in opts]}
    objective=NS(learning_objective_id=7,quarter=1,code='5.1.1.1',title_kz='ҚАЗАҚ МАҚСАТЫ',title_ru='РУССКАЯ ЦЕЛЬ',title_segments_kz=[],title_segments_ru=[])
    return NS(item_id=86,subject_id=1,subject_name='Математика',grade_level=5,quarter=1,
        question_type=AssessmentQuestionType(kind),difficulty=AssessmentQuestionDifficulty.BASIC,
        language=AssessmentLanguage.RUSSIAN,status=QuestionBankItemStatus.REJECTED,origin=QuestionBankItemOrigin.MANUAL,
        title='Авторский заголовок',text=text,text_segments=segments,instruction='Авторская инструкция',
        content=content,answer_key=answer,grading_settings=grading,max_score=(2 if kind in ['matching','ordering'] else 1),
        explanation='Авторское объяснение',author_comment='Авторский комментарий',objectives=[objective],
        reviews=[],created_at=datetime(2026,10,23),updated_at=datetime(2026,10,23),
        author_name='Учитель <ФИО>',author_user_id=2,created_by_user_id=2,is_own=True)


def ctx(locale,kind='single_choice'):
    item=question(kind);obj=item.objectives[0]
    scope=NS(subject_id=1,subject_code='math',subject_name_kz='Математика KZ',subject_name_ru='Математика RU',subject_name='Математика',grade_level=5)
    page=NS(items=[item],total=1,teaching_scope=[scope],learning_objectives=[obj],
        selected_status=None,counters=NS(total=1,draft=0,review=0,ready=0,rejected=1,archived=0),
        filters=NS(subject_id=1,grade_level=5,quarter=1,objective_id=7))
    return dict(request=request(locale),user={'role':'teacher','full_name':'Учитель'},item=item,objectives=[obj],
        page=page,create_context=NS(teaching_scope=[scope]),selected_subject_id=1,selected_grade_level=5,
        selected_quarter=1,selected_objective_id=7,selected_objective=obj,selected_language='ru',
        qb_selected_language='ru',teaching_scope=[scope],subject_id=1,grade_level=5,quarter=1,scope='1:5',
        token='test-token',values={'language':'ru','question_type':kind,'max_score':'1'},
        question_types=list(AssessmentQuestionType),difficulties=list(AssessmentQuestionDifficulty),
        languages=list(AssessmentLanguage),error=None,created_item_id=None)


@pytest.mark.parametrize('locale',['ru','kk'])
@pytest.mark.parametrize('kind',[t.value for t in AssessmentQuestionType])
def test_editor_detail_review_for_all_types(locale,kind):
    env=environment();c=ctx(locale,kind);saved=deepcopy((c['item'].content,c['item'].answer_key,c['item'].grading_settings))
    for page in ['edit.html','detail.html','review.html','catalog.html']:
        html=env.get_template('teacher/assessment/question_bank/'+page).render(**c)
        assert f'<html lang="{locale}">' in html
        assert 'Авторский заголовок' in html
        if page=='edit.html':
            match=re.search(r'id="qb-initial-item"[^>]*data-initial-item="([^"]+)"',html)
            assert match
            payload=json.loads(unescape(match[1]))
            assert payload['question_type']==kind
            assert (payload['content'],payload['answer_key'],payload['grading_settings'])==saved
            assert 'value="ru"' in html
        assert (c['item'].content,c['item'].answer_key,c['item'].grading_settings)==saved


@pytest.mark.parametrize('locale',['ru','kk'])
def test_manual_ai_create_and_lists(locale,tmp_path):
    env=environment();c=ctx(locale)
    for page in ['create.html','ai_create.html','index.html','items.html']:
        html=env.get_template('teacher/assessment/question_bank/'+page).render(**c)
        assert f'<html lang="{locale}">' in html
        if page in ['create.html','ai_create.html']:
            assert ('Математика RU' if locale=='ru' else 'Математика KZ') in html
            # Objective source blocks for both content languages remain available to the picker.
            assert 'РУССКАЯ ЦЕЛЬ' in html and 'ҚАЗАҚ МАҚСАТЫ' in html
        if shutil.which('node'):
            for index,(attrs,source) in enumerate(re.findall(r'<script([^>]*)>(.*?)</script>',html,re.S)):
                if 'src=' in attrs or 'application/json' in attrs:continue
                file=tmp_path/f'{page}.{index}.js';file.write_text(source)
                result=subprocess.run(['node','--check',str(file)],capture_output=True,text=True)
                assert result.returncode==0,result.stderr


def test_macro_imports_bind_request_language():
    env=environment()
    source="""{% from 'teacher/assessment/question_bank/components/objective_preview.html' import objective_language_select with context %}{{ objective_language_select('ru') }}"""
    for locale,expected in [('ru','Язык задания'),('kk','Тапсырма тілі')]:
        html=env.from_string(source).render(request=request(locale))
        assert expected in html
        assert '<option value="ru" selected>' in html


def test_localized_errors_keep_status_and_other_routes_unchanged():
    app=FastAPI();app.add_exception_handler(StarletteHTTPException,question_bank_http_exception_handler)
    @app.get('/teacher/question-bank/test/{code}')
    async def fail(code:int):raise HTTPException(code,detail='technical.validator.unmapped',headers={'X-Test':'kept'})
    @app.get('/other')
    async def other():raise HTTPException(403,detail='Original detail')
    @app.post('/ai/create')
    async def validate(req:Request):return question_bank_validation_response(req,[{'loc':['body','max_score'],'type':'decimal_parsing','input':'SECRET'}])
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            for lang in ['ru','kk']:
                for code in [400,401,403,404]:
                    result=await client.get(f'/teacher/question-bank/test/{code}',headers={'cookie':f'ui_language={lang}'})
                    assert result.status_code==code and result.headers['x-test']=='kept'
                    assert result.headers['content-language']==lang
                    assert result.json()['detail']!='technical.validator.unmapped'
                result=await client.post('/ai/create',headers={'cookie':f'ui_language={lang}'})
                assert result.status_code==422 and 'SECRET' not in result.text
                assert result.json()['detail'][0]['loc']==['body','max_score']
            result=await client.get('/other');assert result.json()['detail']=='Original detail'
    asyncio.run(run())


def test_js_dictionary_and_parameter_substitution(tmp_path):
    if not shutil.which('node'):pytest.skip('Node optional')
    data={'language':'ru','messages':{key:translate(message,'ru') for key,message in QB_WEB_MESSAGES.items()}}
    key=next(key for key,source in QB_WEB_MESSAGES.items() if source=='Дұрыс жауап: {p0}')
    script="const vm=require('vm'),fs=require('fs'),assert=require('assert');\n"
    script+='const data='+json.dumps(data,ensure_ascii=False)+';\n'
    script+="const sandbox={window:{},document:{getElementById:()=>({textContent:JSON.stringify(data)})}};\n"
    script+="vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),sandbox);\n"
    script+='assert.equal(sandbox.window.SchoolMonitorI18n.t('+json.dumps(key)+",{p0:'<x> {p1} Дұрыс жауап'}),'Правильный ответ: <x> {p1} Дұрыс жауап');\n"
    file=tmp_path/'formatter.js';file.write_text(script)
    result=subprocess.run(['node',str(file),str(PROJECT/'app/web/static/js/ui_i18n.js')],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_conditional_grading_labels_translate_in_all_modes():
    env=environment()
    cases=[('matching_grading_summary.html','render_matching_grading_summary','matching'),
           ('ordering_grading_summary.html','render_ordering_grading_summary','ordering'),
           ('fill_gaps_grading_summary.html','render_fill_gaps_grading_summary','fill_gaps')]
    for page,macro,kind in cases:
        for scored in [True,False]:
            item=question(kind)
            if not scored:item.grading_settings={}
            source="{% from 'teacher/assessment/question_bank/components/"+page+"' import "+macro+" with context %}{{ "+macro+"(item) }}"
            text=env.from_string(source).render(request=request('ru'),item=item)
            assert 'Ескі тапсырма' not in text
            assert 'Әр дұрыс' not in text
            assert ('1 балл' in text or '2 балл' in text)


def test_kazakh_content_is_preserved_under_russian_ui():
    c=ctx('ru','single_choice');c['item'].language=AssessmentLanguage.KAZAKH
    c['item'].text='Тапсырманың қазақша мәтіні өзгермесін'
    c['item'].text_segments=[{'type':'text','text':c['item'].text}]
    html=environment().get_template('teacher/assessment/question_bank/edit.html').render(**c)
    source=re.search(r"data-initial-segments='([^']+)'",html)
    assert json.loads(unescape(source[1]))==c['item'].text_segments
    assert 'data-objective-default-language="kk"' in html
    assert 'Редактирование задания' in html


def test_form_actions_and_machine_values_do_not_depend_on_ui_language():
    from html.parser import HTMLParser
    class Fields(HTMLParser):
        def __init__(self):super().__init__();self.fields=[]
        def handle_starttag(self,tag,attrs):
            if tag not in ['form','input','select','option','button']:return
            data=dict(attrs)
            self.fields.append((tag,tuple((k,data.get(k)) for k in ['id','name','type','value','action','method','selected','required','disabled'])))
    env=environment()
    for kind in [t.value for t in AssessmentQuestionType]:
        for page in ['edit.html','detail.html','review.html']:
            fields=[]
            for language in ['ru','kk']:
                parser=Fields();parser.feed(env.get_template('teacher/assessment/question_bank/'+page).render(**ctx(language,kind)))
                fields.append(parser.fields)
            assert fields[0]==fields[1],(kind,page)


def test_ai_status_pages_translate_without_changing_ai_warnings():
    env=environment()
    for locale in ['ru','kk']:
        for status in ['running','completed','failed','pending']:
            for code in ['authentication_error','timeout','validation_error']:
                run=NS(status=status,error_code=code,token='test-token',warnings=['Авторское предупреждение AI'])
                html=env.get_template('teacher/assessment/question_bank/ai_status.html').render(**dict(ctx(locale),run=run,edit_url='/teacher/question-bank/items/86/edit'))
                assert ('Задание AI' if locale=='ru' else 'AI тапсырмасы') in html
                if status=='completed':assert 'Авторское предупреждение AI' in html
                if status=='failed':assert ('Не удалось создать задание.' if locale=='ru' else 'Тапсырманы құру мүмкін болмады.') in html
