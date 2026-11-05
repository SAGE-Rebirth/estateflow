from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings

_pool: ArqRedis | None = None


async def get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


async def enqueue(job: str, *args: Any, job_id: str | None = None) -> None:
    pool = await get_pool()
    await pool.enqueue_job(job, *args, _job_id=job_id)
