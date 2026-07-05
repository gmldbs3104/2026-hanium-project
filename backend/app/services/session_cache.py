import json
import redis.asyncio as aioredis
from typing import Any, Optional
from app.core.config import settings

TTL_SECONDS = 600  # 10분 (REQ-003C)

_redis: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def set_session(key: str, value: Any, ttl: int = TTL_SECONDS) -> None:
    await get_redis().set(key, json.dumps(value, default=str), ex=ttl)


async def get_session(key: str) -> Optional[Any]:
    data = await get_redis().get(key)
    if data is None:
        return None
    return json.loads(data)


async def delete_session(key: str) -> None:
    await get_redis().delete(key)
