from typing import Any

from fastapi import APIRouter
from redis.asyncio import Redis

from app.config import get_settings
from app.services.proxy_pool import build_proxy_pool

router = APIRouter(tags=["proxies"])

EMPTY_STATUS: dict[str, Any] = {
    "enabled": False,
    "configured": False,
    "mode": None,
    "count": 0,
    "alive": 0,
    "in_cooldown": 0,
    "antibot_blocked": 0,
    "entries": [],
}


@router.get("/proxies")
async def get_proxies() -> dict:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        pool = build_proxy_pool(redis, force=True)
        if pool is None:
            return dict(EMPTY_STATUS)
        status = await pool.status()
        status["enabled"] = settings.proxy_enabled
        status["configured"] = True
        return status
    finally:
        await redis.aclose()


@router.post("/proxies/check")
async def check_proxies_now(avito: bool = True) -> dict:
    """Healthcheck пула. ``avito=true`` — дополнительно проверить, пускает ли Авито."""
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        pool = build_proxy_pool(redis, force=True)
        if pool is None:
            return {"checked": 0, "ok": 0, "failed": 0, "avito_checked": False}
        return await pool.check_all(avito=avito)
    finally:
        await redis.aclose()
