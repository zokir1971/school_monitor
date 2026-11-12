"""Domain-separated deterministic codes, protected by the application's SECRET_KEY.
The public nonce is not sufficient to reconstruct a code. Rotation is explicit.
"""
import base64,hashlib,hmac
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError


def key_tag(secret,nonce):
    return hmac.new(secret.encode(),('diagnostic-code-key:v1:'+nonce).encode(),hashlib.sha256).hexdigest()


def check_key(job,secret):
    if not hmac.compare_digest(job.key_tag,key_tag(secret,job.nonce)):
        raise WorkPlanError('Ключ сервера изменился. Восстановите прежний SECRET_KEY. / Сервер кілті өзгерді. Алдыңғы SECRET_KEY мәнін қалпына келтіріңіз.')


def code(secret,job,student_id):
    raw=hmac.new(secret.encode(),f'diagnostic-code:v1:{job.session_id}:{job.nonce}:{student_id}'.encode(),hashlib.sha256).digest()
    # 100 bits of entropy, uppercase alphabet accepted by the existing login.
    value=base64.b32encode(raw).decode()[:20]
    return '-'.join(value[i:i+4] for i in range(0,20,4))
