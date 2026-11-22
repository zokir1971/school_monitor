"""UI integration without connecting to a live school database."""
import asyncio
import ast
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from io import BytesIO
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace

from pypdf import PdfReader
from test_ui_language import PROJECT, environment, request
from app.core.i18n import normalize_language, translate
from app.utils.pdf_code import generate_codes_pdf


def context(locale):
    scope=SimpleNamespace(id=1, name='Школа имени <А> & Б')
    issued=SimpleNamespace(region_name=scope.name, district_name=scope.name, school_name=scope.name,
                           raw_code='L1-ABCD',quota_total=3,expires_at='без срока')
    return dict(request=request(locale),step=2,form={},error='Пароли не совпадают',role='school_admin',
                regions=[scope],districts=[scope],schools=[scope],region=scope,district=scope,school=scope,
                invite_code='L1-ABCD',issued=[issued],count=1,batch_id='test-batch',show_codes=True,saved=False,
                username='test',full_name='<Имя>',iin='123456789012')


def test_all_access_pages_in_both_languages(tmp_path):
    env=environment()
    pages=['auth/register_admin.html','auth/register_staff_schools.html',
           'auth/setup/superuser_register.html','auth/setup/superuser_done.html']
    pages += ['codes/'+f.name for f in (PROJECT/'app/web/templates/codes').glob('*.html')]
    node=shutil.which('node')
    for lang in ['ru','kk']:
        for page in pages:
            html=env.get_template(page).render(**context(lang))
            assert f'<html lang="{lang}">' in html
            assert html.index('id="ui-i18n"') < html.index('<body>')
            if '<Имя>' in html:raise AssertionError('Unescaped registration form value')
            if page.endswith('_result.html'):
                assert 'L1-ABCD' in html
            # Parse rendered inline JavaScript, including template-literal labels.
            if node:
                for index,(attrs,source) in enumerate(re.findall(r'<script([^>]*)>(.*?)</script>',html,re.S)):
                    if 'application/json' in attrs or 'src=' in attrs:continue
                    file=tmp_path/f'{lang}_{index}.js';file.write_text(source,encoding='utf-8')
                    result=subprocess.run([node,'--check',str(file)],capture_output=True,text=True)
                    assert result.returncode==0,(page,result.stderr)
    html=env.get_template('auth/register_admin.html').render(**context('kk'))
    assert 'Құпиясөздер сәйкес келмейді' in html
    assert 'Мектеп әкімшісі' in html
    assert '&lt;Имя&gt;' in html
    assert 'value="test"' in html
    html=env.get_template('auth/register_admin.html').render(**dict(context('ru'), step=1))
    assert 'Код приглашения' in html
    # Never echo a password passed accidentally by a caller.
    html=env.get_template('auth/register_staff_schools.html').render(**dict(context('kk'),form={'password':'SECRET-PASSWORD'}))
    assert 'SECRET-PASSWORD' not in html


def test_preview_language_switch_returns_to_get_entry():
    env=environment();req=request('kk');req.scope['path']='/register-admin/preview'
    html=env.get_template('auth/register_admin.html').render(**dict(context('kk'),request=req))
    assert 'name="next" value="/register-admin"' in html
    assert 'name="next" value="/register-admin/preview"' not in html


def test_success_message_is_a_known_flag():
    env=environment();req=request('kk');req.scope['query_string']=b'registered=1&success=%3Cscript%3Ex%3C/script%3E'
    html=env.get_template('auth/login.html').render(request=req,error=None)
    assert 'Тіркелу сәтті аяқталды' in html
    assert '<script>x</script>' not in html


def test_pdf_language_and_unchanged_codes():
    issued=[{'region_name':'Тест мектебі','raw_code':'L1-ABCD','quota_total':2,'expires_at':'без срока'}]
    for language,label in [('ru','Действует до'),('kk','Жарамдылық мерзімі')]:
        data=generate_codes_pdf(title='Коды регистрации администраторов регионов (L1)',
            issued=issued,level_label='L1',ui_language=language,context_header='Регион')
        text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(data)).pages)
        assert label in ' '.join(text.split())
        assert 'L1-ABCD' in text and 'Тест мектебі' in text
        assert ('мерзімсіз' if language=='kk' else 'без срока') in text


def service_class(path,name,namespace):
    # Execute the actual service class with isolated collaborators. No model-registry import or DB IO.
    source=ast.parse((PROJECT/path).read_text(encoding='utf-8-sig'))
    selected=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name==name)
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),selected],type_ignores=[])
    exec(compile(ast.fix_missing_locations(module),str(path),'exec'),namespace)
    return namespace[name]


def test_registration_services_save_locale_with_user():
    class Roles(Enum):
        SUPERUSER='superuser';SCHOOL_STAFF='school_staff';TEACHER='teacher'
        REGION_ADMIN='region_admin';DISTRICT_ADMIN='district_admin';SCHOOL_ADMIN='school_admin'
    class User:
        iin=username=staff_member_id=email=phone=object()
        def __init__(self,**kw):self.__dict__.update(kw);self.id=9
    class Repo:
        @staticmethod
        async def add(db,user):db.user=user;return user
    async def missing(*args,**kw):return None
    async def no(*args,**kw):return False
    for name in ['get_by_username','get_by_iin','get_by_email','get_by_phone']:
        setattr(Repo,name,missing)
    for name in ['exists_by_username','exists_by_email','exists_by_phone']:
        setattr(Repo,name,no)
    class DB:
        def __init__(self):self.user=None;self.commits=0;self.scalar_calls=0
        async def commit(self):self.commits+=1
        async def flush(self):pass
        async def refresh(self,user):pass
        def add(self,user):self.user=user
        async def scalar(self,query):
            self.scalar_calls+=1
            return SimpleNamespace(id=2,full_name='Учитель',school_id=1,is_active=True) if self.scalar_calls==1 else None
        async def get(self,*args):return SimpleNamespace(id=1)
        def begin(self):return self
        async def __aenter__(self):return self
        async def __aexit__(self,*args):self.commits+=1
    common=dict(User=User,UserRole=Roles,UserRepo=Repo,normalize_language=normalize_language,
                hash_password=lambda value:'hash',utcnow=lambda:datetime.now(timezone.utc),
                validate_user_scope=lambda *args:None,registration_code_lookup_hash=lambda code:code,
                Region=object(),School=object(),District=object())
    async def run():
        db=DB()
        service=service_class('app/modules/users/services/bootstrap.py','BootstrapService',dict(common))
        user=await service.create_superuser(db,username='admin',password_hash='hash',full_name='Имя',iin='123456789012',email='a@b.kz',phone='77771112233',ui_language='kz')
        assert user.ui_language=='kk' and db.commits==1
        class Query:
            def where(self,*args):return self
        staff_ns=dict(common,select=lambda *args:Query(),or_=lambda *args:None,SchoolStaffMember=SimpleNamespace(iin=object()),
                      StaffRegistrationError=ValueError,StaffRegistrationResult=lambda **kw:SimpleNamespace(**kw))
        service=service_class('app/modules/users/services/staff_auth_service.py','StaffAuthService',staff_ns)
        db=DB();dto=SimpleNamespace(iin='123456789012',username='teacher',email='t@b.kz',phone='77771112233',password='12345678',password2='12345678',role=Roles.TEACHER)
        result=await service.register_staff_user(db,dto=dto,ui_language='ru')
        assert result.user.ui_language=='ru' and db.commits==1
        rc=SimpleNamespace(is_active=True,revoked_at=None,expires_at=None,quota_left=2,quota_total=2,target_role=Roles.SCHOOL_ADMIN,school_id=1,id=3)
        async def code(*args):return rc
        async def add_use(db,use):pass
        ns=dict(common,RegistrationCodeRepo=SimpleNamespace(get_by_lookup_hash_for_update=code,add_use=add_use),
                RegistrationCodeUse=lambda **kw:SimpleNamespace(**kw))
        service=service_class('app/modules/users/services/admin_registration.py','AdminRegistrationService',ns)
        db=DB();user=await service.register_admin_with_code(db,code='L3-TEST',username='school',password='12345678',ui_language='kk')
        assert user.ui_language=='kk' and rc.quota_left==1 and db.commits==1
    asyncio.run(run())


def test_admin_error_restores_scope_without_using_invite():
    path=PROJECT/'app/routers/web/auth/register_admin_by_code.py'
    node=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='_context_after_error')
    code=SimpleNamespace(target_role='region_admin',region_id=2)
    calls=[]
    async def preview(db,invite_code):calls.append(invite_code);return code
    class Query:
        def order_by(self,*args):return self
        def where(self,*args):return self
    class Result:
        def scalars(self):return self
        def all(self):return [SimpleNamespace(id=2,name='Область')]
    class DB:
        async def execute(self,query):return Result()
    namespace={'RegistrationCodeService':SimpleNamespace(preview_code=preview),
        'UserRole':SimpleNamespace(REGION_ADMIN='region_admin',DISTRICT_ADMIN='district_admin',SCHOOL_ADMIN='school_admin'),
        'Region':SimpleNamespace(name=object(),id=object()),'select':lambda *args:Query()}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
    result=asyncio.run(namespace['_context_after_error'](DB(),{'step':2,'invite_code':'L1-ABCD','region_id':2,'username':'name'}))
    assert result['role']=='region_admin' and result['regions'][0].id==2
    assert result['username']=='name' and result['region_id']==2
    assert calls==['L1-ABCD']
