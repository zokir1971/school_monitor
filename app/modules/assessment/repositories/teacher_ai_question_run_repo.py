"""SQL operations for durable web requests; transactions belong to services."""
from sqlalchemy import text


class TeacherAIQuestionRunRepo:
    @staticmethod
    async def create(db, *, token, user_id):
        await db.execute(text('INSERT INTO teacher_ai_question_runs(token,user_id) VALUES (:token,:user_id)'),
                         {'token': token, 'user_id': user_id})

    @staticmethod
    async def get(db, *, token, user_id, lock=False):
        sql = 'SELECT r.*, q.status AS item_status, q.language AS item_language FROM teacher_ai_question_runs r LEFT JOIN question_bank_items q ON ' \
              'q.id=r.item_id WHERE r.token=:token AND r.user_id=:user_id'
        if lock:
            sql += ' FOR UPDATE OF r'
        result = await db.execute(text(sql), {'token': token, 'user_id': user_id})
        row = result.mappings().one_or_none()
        return dict(row) if row is not None else None

    @staticmethod
    async def claim(db, *, token, user_id, fingerprint):
        await db.execute(text(
            "UPDATE teacher_ai_question_runs SET status='running',fingerprint=:fingerprint,updated_at=now() WHERE "
            "token=:token AND user_id=:user_id AND status='pending'"),
                         {'token': token, 'user_id': user_id, 'fingerprint': fingerprint})

    @staticmethod
    async def complete(db, *, token, user_id, item_id, warnings, item_ids=None):
        import json
        await db.execute(text(
            "UPDATE teacher_ai_question_runs SET status='completed',item_id=:item_id,item_ids=CAST(:item_ids AS jsonb),warnings=CAST(:warnings AS "
            "jsonb),updated_at=now() WHERE token=:token AND user_id=:user_id AND status='running'"),
                         {'token': token, 'user_id': user_id, 'item_id': item_id,
                          'item_ids': json.dumps(item_ids or [item_id]),
                          'warnings': json.dumps(list(warnings), ensure_ascii=False)})

    @staticmethod
    async def fail(db, *, token, user_id, error_code):
        await db.execute(text(
            "UPDATE teacher_ai_question_runs SET status='failed',error_code=:error_code,updated_at=now() WHERE "
            "token=:token AND user_id=:user_id AND status='running'"),
                         {'token': token, 'user_id': user_id, 'error_code': error_code[:100]})

    @staticmethod
    async def save_proposal(db, *, token, user_id, proposal):
        import json
        await db.execute(text(
            "UPDATE teacher_ai_question_runs SET proposal=CAST(:proposal AS jsonb),updated_at=now() "
            "WHERE token=:token AND user_id=:user_id AND status IN ('running','failed')"),
            {'token':token, 'user_id':user_id, 'proposal':json.dumps(proposal,ensure_ascii=False)})
