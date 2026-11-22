"""Private 30-minute batch cache shared by workers on the same application host.

Immutable payload plus exclusive marker files avoids lost updates between workers.
No registration codes are put into browser cookies or ordinary logs.
"""
import json
import os
from pathlib import Path
import time
from uuid import UUID

_CACHE_TTL = 30 * 60
_CACHE_DIRECTORY = Path(__file__).resolve().parents[4] / '.runtime' / 'registration_batches'
_MAX_BATCHES = 512


def _paths(batch_id):
    try:
        key = str(UUID(str(batch_id)))
    except (ValueError, AttributeError, TypeError):
        return None
    return [_CACHE_DIRECTORY / (key + suffix) for suffix in ('.json', '.shown', '.saved')]


def cache_delete(batch_id):
    paths = _paths(batch_id)
    if paths:
        for path in paths:
            path.unlink(missing_ok=True)


def _prepare():
    _CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True, mode=0o700)
    # This directory is private runtime data, outside static/uploads trees.
    if os.name != 'nt':
        _CACHE_DIRECTORY.chmod(0o700)
    now = time.time()
    files = list(_CACHE_DIRECTORY.glob('*.json'))
    for path in files:
        try:
            expired = now - path.stat().st_mtime > _CACHE_TTL
        except FileNotFoundError:
            continue
        if expired:
            cache_delete(path.stem)
    if len(list(_CACHE_DIRECTORY.glob('*.json'))) >= _MAX_BATCHES:
        raise ValueError('Слишком много недавних выдач. Повторите позже.')


def cache_set(batch_id, data):
    paths = _paths(batch_id)
    if paths is None:
        raise ValueError('Некорректный номер выдачи')
    _prepare()
    payload = dict(data, expires_at_epoch=time.time() + _CACHE_TTL)
    encoded = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    # uuid batch id is new; exclusive creation never replaces another batch.
    fd = os.open(paths[0], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        cache_delete(batch_id)
        raise


def _mark(path):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    os.close(fd)
    return True


def cache_get(batch_id, *, owner_id, level, scope_id=None, claim=False):
    paths = _paths(batch_id)
    if paths is None:
        return None
    try:
        payload = json.loads(paths[0].read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if time.time() >= payload.get('expires_at_epoch', 0):
        cache_delete(batch_id)
        return None
    if (payload.get('owner_id'), payload.get('level'), payload.get('scope_id')) != (owner_id, level, scope_id):
        return None
    shown = paths[1].exists()
    if claim:
        shown = not _mark(paths[1])
    return dict(payload, shown=shown, saved=paths[2].exists(), show_codes=claim and not shown)


def cache_mark_saved(batch_id, *, owner_id, level, scope_id=None):
    if cache_get(batch_id, owner_id=owner_id, level=level, scope_id=scope_id) is not None:
        _mark(_paths(batch_id)[2])
