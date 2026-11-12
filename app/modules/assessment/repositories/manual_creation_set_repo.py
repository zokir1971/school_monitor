"""Constant-count bound SQL; ownership and row locks include each read."""
import json
from sqlalchemy import text

class ManualCreationSetRepo:
    @staticmethod
    async def create(db, *, token, user_id, context, slots):
        await db.execute(text("INSERT INTO qb_manual_creation_sets(token,user_id,context,slots,item_ids) VALUES (:token,:user_id,CAST(:context AS jsonb),CAST(:slots AS jsonb),CAST(:ids AS jsonb)) ON CONFLICT(token) DO NOTHING"),
            dict(token=token,user_id=user_id,context=json.dumps(context),slots=json.dumps(slots),ids=json.dumps([None]*len(slots))))
    @staticmethod
    async def get(db, *, token, user_id, lock=False):
        result=await db.execute(text('SELECT * FROM qb_manual_creation_sets WHERE token=:token AND user_id=:user_id'+(' FOR UPDATE' if lock else '')),dict(token=token,user_id=user_id))
        row=result.mappings().one_or_none()
        return dict(row) if row else None
    @staticmethod
    async def attach(db, *, token, user_id, item_ids):
        await db.execute(text('UPDATE qb_manual_creation_sets SET item_ids=CAST(:ids AS jsonb) WHERE token=:token AND user_id=:user_id'),dict(token=token,user_id=user_id,ids=json.dumps(item_ids)))

    @staticmethod
    async def recent(db, *, user_id):
        result = await db.execute(text('SELECT token,context,item_ids FROM qb_manual_creation_sets WHERE user_id=:user_id ORDER BY created_at DESC LIMIT 10'),dict(user_id=user_id))
        return [dict(r) for r in result.mappings().all()]

    @staticmethod
    async def delete(db, *, token, user_id):
        # Only the owner's planning row is removed; bank items are independent.
        await db.execute(text('DELETE FROM qb_manual_creation_sets WHERE token=:token AND user_id=:user_id'),
                         dict(token=token, user_id=user_id))
