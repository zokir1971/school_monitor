from datetime import timedelta
from sqlalchemy import and_,case,delete,func,insert,or_,select,update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.modules.users.models import User
from app.modules.org.models import District,Region,School
from app.modules.users.models_recovery import AccessRecoveryAudit,AccessRecoveryGrant,AccessRecoveryLimit
from app.modules.users.recovery_policy import recovery_scope

U=User.__table__;G=AccessRecoveryGrant.__table__;A=AccessRecoveryAudit.__table__;L=AccessRecoveryLimit.__table__


async def user(db,user_id,lock=False):
    q=select(U).where(U.c.id==user_id)
    if lock:q=q.with_for_update()
    return (await db.execute(q)).mappings().one_or_none()


async def target(db,actor,user_id,lock=False):
    if lock:
        # Same school-first lock order as transfer, registration and issuance.
        school_id=await db.scalar(select(U.c.school_id).where(U.c.id==user_id))
        if school_id is not None:
            await db.execute(select(School.id).where(School.id==school_id).with_for_update())
    q=select(U).where(U.c.id==user_id,recovery_scope(U,actor))
    if lock:q=q.with_for_update()
    return (await db.execute(q)).mappings().one_or_none()


async def search(db,actor,query):
    S,D,R=School.__table__,District.__table__,Region.__table__
    escaped=query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
    match=(U.c.iin==query) if query.isdigit() and len(query)==12 else or_(U.c.username.ilike(escaped+'%',escape='\\'),U.c.full_name.ilike('%'+escaped+'%',escape='\\'))
    rows=(await db.execute(select(U.c.id,U.c.username,U.c.full_name,U.c.role,U.c.is_active,
            S.c.name.label('school_name'),D.c.name.label('district_name'),R.c.name.label('region_name'))
            .select_from(U.outerjoin(S,S.c.id==U.c.school_id).outerjoin(D,D.c.id==func.coalesce(U.c.district_id,S.c.district_id))
                         .outerjoin(R,R.c.id==func.coalesce(U.c.region_id,D.c.region_id)))
            .where(recovery_scope(U,actor),match).order_by(U.c.full_name,U.c.id).limit(51))).mappings().all()
    return rows[:50],len(rows)>50


async def identifier(db,value,lock=False):
    q=select(U).where(or_(U.c.username==value,U.c.iin==value)).order_by(U.c.id).limit(2)
    if lock:
        school_ids=(await db.execute(select(U.c.school_id).where(or_(U.c.username==value,U.c.iin==value))
            .order_by(U.c.id).limit(2))).scalars().all()
        ids=sorted({sid for sid in school_ids if sid is not None})
        if ids:
            await db.execute(select(School.id).where(School.id.in_(ids)).order_by(School.id).with_for_update())
        q=q.with_for_update()
    rows=(await db.execute(q)).mappings().all()
    return rows[0] if len(rows)==1 else None


async def open_grant(db,user_id,now):
    return (await db.execute(select(G).where(G.c.user_id==user_id,G.c.used_at.is_(None),G.c.revoked_at.is_(None),G.c.expires_at>now)
        .order_by(G.c.id.desc()).limit(1).with_for_update())).mappings().one_or_none()


async def revoke(db,user_id,now):
    await db.execute(update(G).where(G.c.user_id==user_id,G.c.used_at.is_(None),G.c.revoked_at.is_(None)).values(revoked_at=now))


async def create_grant(db,values):
    await db.execute(insert(G).values(**values))


async def use_grant(db,grant_id,now):
    return (await db.execute(update(G).where(G.c.id==grant_id,G.c.used_at.is_(None),G.c.revoked_at.is_(None),G.c.expires_at>now).values(used_at=now).returning(G.c.id))).scalar_one_or_none() is not None


async def replace_password(db,target,hashed):
    return (await db.execute(update(U).where(U.c.id==target['id'],U.c.is_active.is_(True),U.c.password_hash==target['password_hash']).values(password_hash=hashed).returning(U.c.id))).scalar_one_or_none() is not None


async def audit(db,actor_id,target_id,action):
    await db.execute(insert(A).values(actor_user_id=actor_id,target_user_id=target_id,action=action))


async def history(db,actor):
    return (await db.execute(select(A.c.created_at,A.c.action,U.c.username,U.c.full_name).select_from(A.outerjoin(U,U.c.id==A.c.target_user_id))
        .where(or_(recovery_scope(U,actor),and_(A.c.actor_user_id==actor['id'],A.c.target_user_id.is_(None))))
        .order_by(A.c.id.desc()).limit(50))).mappings().all()


async def rate(db,key,now,maximum):
    expired=L.c.resets_at<=now
    q=pg_insert(L).values(bucket_key=key,attempts=1,resets_at=now+timedelta(minutes=1))
    q=q.on_conflict_do_update(index_elements=[L.c.bucket_key],set_={
        'attempts':case((expired,1),else_=L.c.attempts+1),
        'resets_at':case((expired,now+timedelta(minutes=1)),else_=L.c.resets_at),
    }).returning(L.c.attempts)
    count=(await db.execute(q)).scalar_one()
    # Bounded cleanup prevents unbounded growth from abandoned IP buckets.
    stale=select(L.c.bucket_key).where(L.c.resets_at<now-timedelta(days=1)).limit(100)
    await db.execute(delete(L).where(L.c.bucket_key.in_(stale)))
    return count<=maximum
