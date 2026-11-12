"""Constant query count, independent of field/objective/answer count."""
import json
from sqlalchemy import text

class QuestionTranslationRequestRepo:
    @staticmethod
    async def get(db, *, item_id, source_hash, language, user_id):
        result=await db.execute(text('''SELECT status, values_json, error_code, attempt_token,
            updated_at < now() - interval '15 minutes' AS expired
            FROM qb_translation_requests WHERE item_id=:item_id AND source_hash=:source_hash
            AND language=:language AND user_id=:user_id'''),locals_params(item_id,source_hash,language,user_id))
        return result.mappings().one_or_none()

    @staticmethod
    async def claim(db, *, item_id, source_hash, language, user_id, attempt_token):
        params=locals_params(item_id,source_hash,language,user_id);params['attempt_token']=attempt_token
        result=await db.execute(text('''INSERT INTO qb_translation_requests AS r
            (item_id,source_hash,language,user_id,attempt_token,status)
            VALUES (:item_id,:source_hash,:language,:user_id,:attempt_token,'running')
            ON CONFLICT (item_id,source_hash,language) DO UPDATE
            SET attempt_token=EXCLUDED.attempt_token,status='running',values_json=NULL,
                error_code=NULL,updated_at=now()
            WHERE r.user_id=EXCLUDED.user_id AND r.attempt_token<>EXCLUDED.attempt_token
            AND (r.status='failed' OR (r.status='running' AND r.updated_at < now()-interval '15 minutes'))
            RETURNING attempt_token'''),params)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def finish(db, *, item_id, source_hash, language, user_id, attempt_token, values=None, error_code=None):
        params=locals_params(item_id,source_hash,language,user_id)
        params.update(attempt_token=attempt_token,status='failed' if error_code else 'proposed',
            values_json=json.dumps(values,ensure_ascii=False) if values is not None else None,error_code=error_code)
        await db.execute(text('''UPDATE qb_translation_requests SET status=:status,
            values_json=CAST(:values_json AS jsonb),error_code=:error_code,updated_at=now()
            WHERE item_id=:item_id AND source_hash=:source_hash AND language=:language
            AND user_id=:user_id AND attempt_token=:attempt_token AND status='running' '''),params)


def locals_params(item_id,source_hash,language,user_id):
    return dict(item_id=item_id,source_hash=source_hash,language=language,user_id=user_id)
