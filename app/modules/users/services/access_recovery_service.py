"""Shared recovery workflow: no commits here; routes own the transaction."""
import asyncio
from datetime import datetime,timedelta,timezone
import hashlib
import hmac
import re
import secrets
from app.core.config import get_settings
from app.core.security import hash_password,verify_password
from app.core.access_session import credential_stamp
from app.modules.users.recovery_policy import ADMIN_ROLES,role_value
from app.modules.users.repositories import access_recovery_repo as repo


class RecoveryError(Exception):
    def __init__(self,code):
        self.code=code
        super().__init__(code)


def now():return datetime.now(timezone.utc)


def valid_password(password,confirmation):
    if password!=confirmation:raise RecoveryError('password_mismatch')
    if len(password)<8 or len(password.encode('utf-8'))>1024:raise RecoveryError('password_length')


def digest_code(raw):
    normalized=re.sub(r'[\s-]','',raw).upper()
    if not re.fullmatch(r'R1[0-9A-F]{32}',normalized):return None
    return hashlib.sha256(normalized.encode()).hexdigest()


def rate_key(category,identifier):
    return hmac.new(str(get_settings().SECRET_KEY).encode(),(category+'|'+str(identifier)).encode(),hashlib.sha256).hexdigest()


async def admin(db,user_id):
    actor=await repo.user(db,user_id)
    if not actor or not actor['is_active'] or role_value(actor['role']) not in ADMIN_ROLES:raise RecoveryError('forbidden')
    return actor


async def search(db,user_id,query):
    actor=await admin(db,user_id)
    if not await repo.rate(db,rate_key('search',user_id),now(),60):raise RecoveryError('rate')
    query=query.strip()
    if not 3<=len(query)<=120:raise RecoveryError('query')
    rows,overflow=await repo.search(db,actor,query)
    await repo.audit(db,user_id,None,'lookup')
    return rows,overflow


async def issue(db,user_id,target_id):
    actor=await admin(db,user_id)
    if not await repo.rate(db,rate_key('issue',user_id),now(),30):raise RecoveryError('rate')
    target=await repo.target(db,actor,target_id,lock=True)
    if not target:raise RecoveryError('not_found')
    if not target['is_active']:raise RecoveryError('inactive')
    issued_at=now();expires_at=issued_at+timedelta(minutes=30)
    digits=secrets.token_hex(16).upper();code='R1-'+'-'.join(digits[i:i+8] for i in range(0,32,8))
    await repo.revoke(db,target_id,issued_at)
    await repo.create_grant(db,dict(user_id=target_id,issued_by_user_id=user_id,token_hash=digest_code(code),
        credential_stamp=credential_stamp(target),issuer_stamp=credential_stamp(actor),expires_at=expires_at))
    await repo.audit(db,user_id,target_id,'issue')
    return dict(id=target['id'],username=target['username'],full_name=target['full_name'],code=code,expires_at=expires_at)


async def redeem(db,identifier,code,password,confirmation,client):
    valid_password(password,confirmation)
    if not await repo.rate(db,rate_key('redeem',client),now(),60):raise RecoveryError('rate')
    identifier=identifier.strip()
    if not 1<=len(identifier)<=120:raise RecoveryError('invalid')
    target=await repo.identifier(db,identifier,lock=True)
    if not target or not target['is_active']:
        await repo.audit(db,None,None,'failed')
        raise RecoveryError('invalid')
    grant=await repo.open_grant(db,target['id'],now())
    digest=digest_code(code)
    if not grant or not digest or not hmac.compare_digest(grant['token_hash'],digest):
        await repo.audit(db,None,target['id'],'failed')
        raise RecoveryError('invalid')
    issuer=await repo.user(db,grant['issued_by_user_id'])
    authorized=await repo.target(db,issuer,target['id']) if issuer else None
    if not authorized or not issuer['is_active'] or not hmac.compare_digest(grant['credential_stamp'],credential_stamp(target)) or not hmac.compare_digest(grant['issuer_stamp'],credential_stamp(issuer)):
        await repo.revoke(db,target['id'],now())
        await repo.audit(db,None,target['id'],'failed')
        raise RecoveryError('invalid')
    hashed=await asyncio.to_thread(hash_password,password)
    if not await repo.use_grant(db,grant['id'],now()):raise RecoveryError('invalid')
    if not await repo.replace_password(db,target,hashed):raise RuntimeError('Recovery password update conflict')
    await repo.revoke(db,target['id'],now())
    await repo.audit(db,issuer['id'],target['id'],'reset')
    return target['username']


async def change_password(db,user_id,current,password,confirmation):
    valid_password(password,confirmation)
    if not await repo.rate(db,rate_key('change',user_id),now(),10):raise RecoveryError('rate')
    target=await repo.user(db,user_id,lock=True)
    if not target or not target['is_active']:raise RecoveryError('forbidden')
    if not await asyncio.to_thread(verify_password,current,target['password_hash']):raise RecoveryError('current_password')
    hashed=await asyncio.to_thread(hash_password,password)
    if not await repo.replace_password(db,target,hashed):raise RuntimeError('Password update conflict')
    await repo.revoke(db,user_id,now())
    await repo.audit(db,user_id,user_id,'change')
    return dict(target,password_hash=hashed)
