"""Живой прогресс обхода в Redis (для прогресс-баров в панели)."""

import contextlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

PROGRESS_TTL_SECONDS = 3600
PROGRESS_KEY_PREFIX = "crawl:progress:"
MAX_PAGES_KEY = "max_pages"

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

STAGES = (
    "queued",
    "pausing",
    "crawl",
    "descriptions",
    "moderation",
    "analytics",
    "matching",
    "alerts",
    "done",
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def progress_key(search_id: uuid.UUID | str) -> str:
    return f"{PROGRESS_KEY_PREFIX}{search_id}"


class CrawlProgress:
    """Хеш в Redis: статус, стадия, страница, счётчики, время."""

    def __init__(self, redis: Redis, search_id: uuid.UUID | str) -> None:
        self._redis = redis
        self._key = progress_key(search_id)

    async def _write(self, mapping: dict[str, Any]) -> None:
        values = {key: str(value) for key, value in mapping.items() if value is not None}
        if not values:
            return
        await self._redis.hset(self._key, mapping=values)  # type: ignore[arg-type]
        await self._redis.expire(self._key, PROGRESS_TTL_SECONDS)

    async def queued(self, search_name: str | None = None) -> None:
        """Сразу после постановки в очередь: UI видит «в очереди», а не пустоту."""
        await self._redis.delete(self._key)
        await self._write(
            {
                "status": STATUS_QUEUED,
                "stage": "queued",
                "search_name": search_name,
                "queued_at": _now_iso(),
                "started_at": _now_iso(),
                "updated_at": _now_iso(),
            }
        )

    async def start(self, max_pages: int, search_name: str | None = None) -> None:
        await self._redis.delete(self._key)
        await self._write(
            {
                "status": STATUS_RUNNING,
                "stage": "crawl",
                "page": 0,
                MAX_PAGES_KEY: max_pages,
                "listings_seen": 0,
                "search_name": search_name,
                "started_at": _now_iso(),
                "updated_at": _now_iso(),
            }
        )

    async def page(self, page_number: int, listings_seen: int) -> None:
        await self._write(
            {
                "page": page_number,
                "listings_seen": listings_seen,
                "updated_at": _now_iso(),
            }
        )

    async def stage(self, stage: str) -> None:
        await self._write({"stage": stage, "updated_at": _now_iso()})

    async def finish(self, result: dict[str, Any]) -> None:
        await self._write(
            {
                "status": STATUS_DONE,
                "stage": "done",
                "result": json.dumps(result, ensure_ascii=False, default=str),
                "updated_at": _now_iso(),
                "finished_at": _now_iso(),
            }
        )

    async def fail(self, error: str) -> None:
        await self._write(
            {
                "status": STATUS_FAILED,
                "error": error[:500],
                "updated_at": _now_iso(),
                "finished_at": _now_iso(),
            }
        )


async def read_progress(redis: Redis, search_id: uuid.UUID | str) -> dict[str, Any] | None:
    data = await redis.hgetall(progress_key(search_id))
    if not data:
        return None
    decoded: dict[str, Any] = {
        (key.decode() if isinstance(key, bytes) else key): (
            value.decode() if isinstance(value, bytes) else value
        )
        for key, value in data.items()
    }
    for numeric in ("page", MAX_PAGES_KEY, "listings_seen"):
        if numeric in decoded:
            with contextlib.suppress(ValueError):
                decoded[numeric] = int(decoded[numeric])
    if "result" in decoded:
        with contextlib.suppress(TypeError, ValueError):
            decoded["result"] = json.loads(decoded["result"])
    return decoded


async def list_running_progress(redis: Redis) -> list[dict[str, Any]]:
    """Все активные обходы (для дашборда)."""
    running: list[dict[str, Any]] = []
    async for key in redis.scan_iter(f"{PROGRESS_KEY_PREFIX}*"):
        data = await read_progress(redis, key.decode().removeprefix(PROGRESS_KEY_PREFIX))
        if data and data.get("status") in (STATUS_QUEUED, STATUS_RUNNING):
            data["search_id"] = key.decode().removeprefix(PROGRESS_KEY_PREFIX)
            running.append(data)
    return running
