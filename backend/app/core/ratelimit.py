"""Fixed-window rate limits in Redis. Fails open: a Redis outage never locks users out."""

import time

import redis.asyncio as redis
import structlog
from fastapi import HTTPException, Request, status

from app.core.config import get_settings

log = structlog.get_logger()
_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(get_settings().redis_url, socket_timeout=0.5)
    return _client


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def hit(name: str, identity: str, limit: int, window_seconds: int) -> None:
    """Count one attempt for (name, identity); raise 429 once `limit` is exceeded."""
    bucket = int(time.time() // window_seconds)
    key = f"rl:{name}:{identity.lower()}:{bucket}"
    try:
        async with get_redis().pipeline(transaction=True) as pipe:
            count, _ = await pipe.incr(key).expire(key, window_seconds + 1).execute()
    except redis.RedisError:
        log.warning("rate_limit_unavailable", name=name)
        return
    if count > limit:
        retry_after = window_seconds - int(time.time() % window_seconds)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many attempts. Please wait and try again.",
            headers={"Retry-After": str(retry_after)},
        )


class RateLimit:
    """Per-IP limit as a route dependency: `dependencies=[Depends(RateLimit("x", 10, 60))]`."""

    def __init__(self, name: str, limit: int, window_seconds: int) -> None:
        self.name, self.limit, self.window = name, limit, window_seconds

    async def __call__(self, request: Request) -> None:
        await hit(self.name, client_ip(request), self.limit, self.window)
