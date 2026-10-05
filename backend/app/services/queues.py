"""Здоровье системы: глубина очередей dramatiq и живость воркера (Redis)."""

import time
from typing import Any

from redis.asyncio import Redis

HEARTBEAT_KEY = "dramatiq:__heartbeats__"
STREAM_SUFFIX = ".msgs"
DELAYED_SUFFIX = ".XQ"
DEFAULT_WORKER_WINDOW_SECONDS = 120


async def queue_depth(redis: Redis, queue_key: str) -> int:
    """Глубина очереди: сообщения в потоке + отложенные/повторные.

    Dramatiq в Redis хранит очередь как stream ``<queue>.msgs`` и zset отложенных
    ``<queue>.XQ``; самого ключа ``<queue>`` не существует (нельзя читать LLEN).
    """
    pipe = redis.pipeline()
    pipe.xlen(f"{queue_key}{STREAM_SUFFIX}")
    pipe.zcard(f"{queue_key}{DELAYED_SUFFIX}")
    try:
        stream_len, delayed = await pipe.execute()
    except Exception:  # noqa: BLE001 — метрика не должна ронять дашборд
        return 0
    try:
        return int(stream_len or 0) + int(delayed or 0)
    except (TypeError, ValueError):
        return 0


async def worker_alive(
    redis: Redis, *, window_seconds: int = DEFAULT_WORKER_WINDOW_SECONDS
) -> bool:
    """Живой ли воркер: последний heartbeat не старше окна (секунды)."""
    try:
        rows = await redis.zrange(HEARTBEAT_KEY, -1, -1, withscores=True)
    except Exception:  # noqa: BLE001
        return False
    if not rows:
        return False
    try:
        score = float(rows[0][1])
    except (TypeError, ValueError):
        return False
    return (time.time() - score) < max(1, window_seconds)


async def system_health(redis: Redis, *, window_seconds: int) -> dict[str, Any]:
    """Сводка для дашборда: воркер и глубина очередей crawl/analytics."""
    return {
        "worker_alive": await worker_alive(redis, window_seconds=window_seconds),
        "crawl_queue": await queue_depth(redis, "dramatiq:crawl"),
        "analytics_queue": await queue_depth(redis, "dramatiq:analytics"),
    }
