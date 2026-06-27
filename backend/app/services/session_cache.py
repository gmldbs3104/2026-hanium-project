import time
from typing import Any, Optional

# 임시 인메모리 캐시: {key: (value, expire_at)}
_cache: dict[str, tuple[Any, float]] = {}

TTL_SECONDS = 600  # 10분 (REQ-003C 관련 명시 사항)


def set_session(key: str, value: Any, ttl: int = TTL_SECONDS) -> None:
    _cache[key] = (value, time.time() + ttl)


def get_session(key: str) -> Optional[Any]:
    item = _cache.get(key)
    if item is None:
        return None
    value, expire_at = item
    if time.time() > expire_at:
        _cache.pop(key, None)
        return None
    return value


def delete_session(key: str) -> None:
    _cache.pop(key, None)