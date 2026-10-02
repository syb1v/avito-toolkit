from typing import Any

from fastapi import APIRouter
from redis.asyncio import Redis

from app.config import get_settings
from app.services.proxy_pool import build_proxy_pool

router = APIRouter(tags=["proxies"])

EMPTY_STATUS: dict[str, Any] = {
    "enabled": False,
    "mode": None,
    "count": 0,
    "alive": 0,
    "in_cooldown": 0,
    "entries": [],
}


@router.get("/proxies")
async def get_proxies() -> dict:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        pool = build_proxy_pool(redis)
        if pool is None:
            return dict(EMPTY_STATUS)
        return await pool.status()
    finally:
        await redis.aclose()


@router.post("/proxies/check")
async def check_proxies_now() -> dict:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        pool = build_proxy_pool(redis)
        if pool is None:
            return {"checked": 0, "ok": 0, "failed": 0}
        return await pool.check_all()
    finally:
        await redis.aclose()
