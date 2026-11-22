"""School-bound, expiring, single-use import previews. No database writes."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time

from fastapi import HTTPException

ROOT = Path(tempfile.gettempdir()) / 'school_monitor_import_previews275'
TTL = 3600
MAX_BYTES = 15 * 1024 * 1024


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def cleanup():
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    for path in ROOT.iterdir():
        if path.suffix not in ('.json', '.claimed'):
            continue
        try:
            if time.time() - path.stat().st_mtime > TTL:
                path.unlink(missing_ok=True)
        except FileNotFoundError:
            pass


def stage(payload, kind):
    cleanup()
    token = secrets.token_hex(32)
    data = dict(payload, kind=kind, created=time.time())
    fd = os.open(ROOT / (token + '.json'), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False)
    return token


def load(token, user, kind):
    cleanup()
    if not re.fullmatch('[0-9a-f]{64}', token):
        raise ValueError('Некорректный предпросмотр. Загрузите файл снова.')
    path = ROOT / (token + '.json')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise ValueError('Предпросмотр истёк или уже использован. Загрузите файл снова.') from exc
    if data['kind'] != kind or data['user_id'] != user.id or data['school_id'] != user.school_id:
        raise HTTPException(403, 'Предпросмотр принадлежит другому пользователю или школе.')
    if not 0 <= time.time() - data['created'] < TTL:
        path.unlink(missing_ok=True)
        raise ValueError('Предпросмотр истёк. Загрузите файл снова.')
    return data, path


def claim(path):
    """Atomic removal from the available queue, including across worker processes."""
    claimed = path.with_name(path.stem + '.' + secrets.token_hex(8) + '.claimed')
    try:
        path.rename(claimed)
    except FileNotFoundError as exc:
        raise ValueError('Предпросмотр уже использован. Загрузите файл снова.') from exc
    return claimed


def csrf_token(request, cookie):
    token = request.cookies.get(cookie, '')
    return token if re.fullmatch('[0-9a-f]{64}', token) else secrets.token_hex(32)


def check_csrf(request, form, cookie):
    token = request.cookies.get(cookie, '')
    if not re.fullmatch('[0-9a-f]{64}', token) or not secrets.compare_digest(token, str(form.get('csrf', ''))):
        raise HTTPException(403, 'Обновите страницу и повторите отправку.')


def summary(total, new, existing):
    # A full new-school load is legitimate; unusual volume requires explicit review.
    return dict(total=total, new=new, matched=total-new, existing=existing,
                risky=total >= 10 and new * 2 > total)


def confirm(form, school_id, stats):
    if str(form.get('school_id_confirmation', '')).strip() != str(school_id):
        raise ValueError('Введите ID школы назначения из предпросмотра.')
    if form.get('confirm_school') != 'yes':
        raise ValueError('Подтвердите принадлежность файла школе назначения.')
    if stats['risky'] and form.get('confirm_new_records') != 'yes':
        raise ValueError('Большинство записей новые. Проверьте файл и подтвердите добавление.')
