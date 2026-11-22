import asyncio
from copy import deepcopy
from datetime import datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace as NS

import httpx
import pytest
from fastapi import FastAPI,HTTPException,Request
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.assessment_i18n import application_http_exception_handler,assessment_validation_response
from app.modules.assessment.enums import (AssessmentStatus,AssessmentType,AssessmentMode,AssessmentCheckpoint,
    AssessmentParticipationStatus,AssessmentAnswerStatus,AssessmentQuestionType)
from test_ui_language import environment,request,PROJECT

PAGES = [
 'teacher/assessment/create.html','teacher/assessment/list.html','teacher/assessment/analytics.html',
 'teacher/assessment/class_assessments.html','teacher/assessment/student_results.html',
 'teacher/assessment/objective_analytics.html','teacher/assessment/objective_students.html',
 'teacher/assessment/online/list.html','teacher/assessment/online/groups.html',
 'teacher/assessment/online/students.html','teacher/assessment/online/student_review.html',
 'staff/assessment/create.html','staff/assessment/list.html','staff/assessment/manual_entry.html',
 'staff/assessment/analytics.html','staff/assessment/dynamics.html','district/assessment/analytics.html',
 'district/assessment/dynamics.html','region/assessment/analytics.html','region/assessment/dynamics.html']


def fixture(language,has_data=True):
    now=datetime(2026,10,23)
    point=NS(checkpoint=AssessmentCheckpoint.BASELINE,checkpoint_label='Нөлдік бақылау',quality_percent=100,
        quality_percent_display='100,00%',delta_baseline_pp=0,delta_previous_pp=0,
        delta_baseline_display='0,00 п.п.',delta_previous_display='—',participated_students=1,total_students=1,
        quality_students=1,participation_display='1 / 1')
    metrics=dict(total_students=1,participated_students=1,absent_students=0,grade_2_count=0,grade_3_count=0,
        grade_4_count=1,grade_5_count=0,quality_percent_display='100,00%',achievement_percent_display='100,00%',
        average_percent_display='80,00%',average_score_display='8,00',participation_display='1 / 1',
        entity_id=1,entity_name='Школа <А> & Б',points=[point])
    metric=NS(**metrics)
    objective=NS(assessment_objective_id=7,learning_objective_id=8,code='5.1.1.1',title='Авторская формулировка цели',
        objective_code='5.1.1.1',objective_title='Авторская формулировка цели',max_score=10,max_score_display='10,00',
        objective_max_score_display='10,00',mastery_percent_display='80,00%',max_score_sum_display='10,00',score_sum_display='8,00',participated_students=1)
    student=NS(student_id=2,assessment_student_id=3,student_name='Ученик <Имя>',student_name_display='Ученик <Имя>',
        participation_status=AssessmentParticipationStatus.COMPLETED,participation_status_label='Орындалды',participation_status_display='Орындалды',
        score=8,score_display='8,00',percent=80,percent_display='80,00%',grade='4',grade_display='4',
        max_score=10,max_score_display='10,00',objective_results={7:NS(score=8,score_display='8,00')})
    row=NS(**metrics,assessment_id=1,assessment_group_id=2,title='Авторское название работы',subject_name='Авторский предмет',
        assessment_type_label='Бақылау жұмысы',input_mode_label='Қолмен енгізу',status=AssessmentStatus.COMPLETED,
        status_label='Аяқталды',status_display='Аяқталды',subject_display='Авторский предмет',class_names_display='5А',teacher_names_display='Учитель <Имя>',
        class_name='5А',class_display='5А',grade_level=5,academic_year_start=2026,school_class_id=1,
        can_complete=False,max_score_display='10,00',processed_students=1,pending_students=0,result_progress_display='100%',
        assigned_count=0,completed_count=1,completion_percent=100,finished_count=1,group_count=1,in_progress_count=0,
        pending_review_count=1,has_pending_review=True,absent_count=0,excused_count=0,not_completed_count=0,
        student_id=2,assessment_student_id=3,student_name_display='Ученик <Имя>',participation_status=AssessmentParticipationStatus.COMPLETED,
        participation_status_display='Орындалды',assigned_at=now,started_at=now,completed_at=now,can_view_answers=True,
        requires_review=True,has_result=True,grade_display='4',percent_display='80,00%',score_display='8,00')
    school_class=NS(id=1,name='5А',academic_year_label='2026–2027',grade_level=5,school_class_id=1,class_name='5А',**metrics)
    subject=NS(id=1,subject_id=1,name_kz='Пән KZ',name_ru='Предмет RU',subject_name='Авторский предмет')
    assessment=NS(title='Авторское название работы',subject_name='Авторский предмет',assessment_type_label='Бақылау жұмысы',
        assessment_mode=AssessmentMode.ASSESSMENT_BY_SECTION,status=AssessmentStatus.DRAFT,status_label='Жоба',
        description='Авторское описание',duration_minutes=30,has_objectives=True,max_score=10,max_score_display='10,00',objectives=[objective])
    dto=NS(is_online=True,school_class_id=1,assessment_count=1,items=[objective],objective_count=1,
        mastery_percent_display='80,00%',max_score_sum_display='10,00',participated_students=1,score_sum_display='8,00',
        grade_display='4',participation_status=AssessmentParticipationStatus.COMPLETED,participation_status_display='Орындалды',percent_display='80,00%',score_display='8,00')
    answer=NS(answer_id=4,question_order_no=1,question_text='Авторский текст задания',question_type=AssessmentQuestionType.MANUAL_REVIEW,
        requires_manual_review=True,max_score=10,max_score_display='10,00',score_display='8,00',is_correct=None,
        status=AssessmentAnswerStatus.PENDING_REVIEW,answer_data={'text':'Ответ ученика <x>'})
    dynamics=NS(has_data=has_data,points=[point] if has_data else [],baseline_quality_percent_display='100,00%',
        latest_quality_percent_display='100,00%',total_delta_baseline_display='0,00 п.п.',point_count=1)
    counts=dict(total_count=1,draft_count=0,completed_count=1,class_count=1,student_count=1,item_count=1,
        district_count=1,school_count=1,total_assessments=1,total_groups=1,total_students=1,assigned_count=0,
        in_progress_count=0,pending_review_count=1,checked_count=0,total_answers=1,
        assessments_with_pending_review_count=1,groups_with_pending_review_count=1)
    return dict(request=request(language),user={'role':'teacher','full_name':'Учитель <Имя>'},
        selected_academic_year=2026,academic_year_start=2026,academic_year_label='2026–2027',academic_years=[2026],
        selected_grade_level=5,grade_level=5,grade_levels=[5],selected_subject_id=1,selected_district_id=1,
        subjects=[subject],classes=[school_class] if has_data else [],students=[student] if has_data else [],
        items=[row] if has_data else [],districts=[metric] if has_data else [],schools=[metric] if has_data else [],
        assessment_statuses=list(AssessmentStatus),assessment_types=list(AssessmentType),assessment_modes=list(AssessmentMode),
        assessment_checkpoints=list(AssessmentCheckpoint),participation_statuses=list(AssessmentParticipationStatus),
        assessment=assessment,groups=[NS(class_name='5А',academic_year_start=2026,teacher_name='Учитель',students=[student])] if has_data else [],
        dto=dto,answers=[answer] if has_data else [],objective_analytics=NS(objective_count=1,objectives=[objective]),
        title='Авторское название работы',subject_name='Авторский предмет',class_name='5А',max_score_display='10,00',
        assessment_group_id=2,assessment_id=1,assessment_student_id=3,student_name='Ученик <Имя>',has_objectives=True,
        objective_code='5.1.1.1',objective_title='Авторская формулировка цели',objective_max_score_display='10,00',
        dynamics=dynamics,school_dynamics=dynamics,region_dynamics=dynamics,district_dynamics=dynamics,
        teacher_analytics=metric,school_analytics=metric,region_analytics=metric,district_analytics=metric,
        points=[point] if has_data else [],subject_class_map={'1':[1]},selected_class_ids=[1],selected_objective_ids=[8],
        selected_assessment_mode='assessment_by_section',selected_checkpoint='baseline',form_data={},
        has_pending_review=True,objective_mode=True,is_completed=False,can_create=True,can_export=True,
        error=None,success=None,filter_action='/filter',clear_url='/clear',create_url='/create',export_url='/export',
        form_action='/save',back_url='/back',manual_route_name='manual',complete_route_name='complete',**counts)


@pytest.mark.parametrize('page',PAGES)
@pytest.mark.parametrize('language',['ru','kk'])
def test_pages_render_populated_and_empty(page,language,tmp_path):
    env=environment();node=shutil.which('node')
    for has_data in [True,False]:
        data=fixture(language,has_data);before=deepcopy((data['assessment'].__dict__,data['students'],data['items']))
        html=env.get_template(page).render(**data)
        assert f'<html lang="{language}">' in html
        assert '<Имя>' not in html
        if page.endswith('create.html'):
            assert ('Предмет RU' if language=='ru' else 'Пән KZ') in html
        if node:
            for i,(attrs,source) in enumerate(re.findall(r'<script([^>]*)>(.*?)</script>',html,re.S)):
                if 'src=' in attrs or 'application/json' in attrs:continue
                path=tmp_path/f'{i}.js';path.write_text(source)
                result=subprocess.run([node,'--check',str(path)],capture_output=True,text=True)
                assert result.returncode==0,(page,result.stderr)
        assert (data['assessment'].__dict__,data['students'],data['items'])==before


def test_assessment_errors_are_scoped_and_keep_status():
    app=FastAPI();app.add_exception_handler(StarletteHTTPException,application_http_exception_handler)
    @app.get('/staff/assessment/test/{code}')
    async def fail(code:int):raise HTTPException(code,detail='internal.error.unmapped')
    @app.get('/other')
    async def other():raise HTTPException(403,detail='Original')
    @app.post('/teacher/assessment/test')
    async def validate(req:Request):return assessment_validation_response(req,[{'loc':['body','max_score'],'type':'decimal_parsing','input':'SECRET'}])
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            for lang in ['ru','kk']:
                for code in [400,401,403,404]:
                    r=await client.get(f'/staff/assessment/test/{code}',headers={'cookie':f'ui_language={lang}'})
                    assert r.status_code==code and r.headers['content-language']==lang
                    assert r.json()['detail']!='internal.error.unmapped'
                r=await client.post('/teacher/assessment/test',headers={'cookie':f'ui_language={lang}'})
                assert r.status_code==422 and 'SECRET' not in r.text
                assert r.json()['detail'][0]['loc']==['body','max_score']
            assert (await client.get('/other')).json()['detail']=='Original'
    asyncio.run(run())


def test_form_actions_values_and_result_numbers_are_language_independent():
    class Fields(HTMLParser):
        def __init__(self):super().__init__();self.fields=[]
        def handle_starttag(self,tag,attrs):
            if tag in ['input','form','select','option','button']:
                d=dict(attrs);self.fields.append((tag,tuple((k,d.get(k)) for k in ['id','name','value','action','method','type','selected','required','disabled','min','max','step'])))
    env=environment()
    for page in PAGES:
        snapshots=[]
        for language in ['ru','kk']:
            data=fixture(language);html=env.get_template(page).render(**data)
            parser=Fields();parser.feed(html);snapshots.append(parser.fields)
            # Authored names/objective texts are never passed through gettext.
            assert 'Ученик <Имя>' not in html
        assert snapshots[0]==snapshots[1],page


def test_known_error_translates_and_question_bank_dispatch_is_preserved():
    from app.core.assessment_i18n import assessment_error_message
    assert assessment_error_message(request('ru'),'Баллды енгізіңіз.',400)=='Введите балл.'
    app=FastAPI();app.add_exception_handler(StarletteHTTPException,application_http_exception_handler)
    @app.get('/teacher/question-bank/test')
    async def fail():raise HTTPException(400,detail='Кемінде бір дұрыс жауапты таңдаңыз.')
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            r=await client.get('/teacher/question-bank/test',headers={'cookie':'ui_language=ru'})
            assert r.status_code==400 and r.json()['detail']=='Выберите хотя бы один правильный ответ.'
    asyncio.run(run())
