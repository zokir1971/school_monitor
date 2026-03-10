import time
from typing import Any

_ISSUE_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = 30 * 60  # 30 минут


def cache_key(namespace: str, batch_id: str) -> str:
    return f"{namespace}:{batch_id}"


def cache_set(batch_id: str, data: dict) -> None:
    _ISSUE_CACHE[batch_id] = {
        "__ts": time.time(),
        **data,
    }


def cache_get(batch_id: str) -> dict | None:
    obj = _ISSUE_CACHE.get(batch_id)
    if not obj:
        return None
    if time.time() - obj["__ts"] > _CACHE_TTL:
        _ISSUE_CACHE.pop(batch_id, None)
        return None
    return obj
