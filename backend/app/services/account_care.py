"""Уход за аккаунтами: дневной лимит активности, «отдых» и «прогрев».

Идея простая: аккаунт — это как человек. Если он вдруг делает 300 страниц в час,
Авито это видит. Мы ведём счётчик страниц за день, отправляем аккаунт «отдохнуть»
после лимита или челленджа и иногда мягко «прогреваем» (заходим на главную и
одну выдачу с человеческими паузами), чтобы сессия выглядела живой.
"""

import time
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

LAST_ACTIVITY_PREFIX = "account:last:"
REST_UNTIL_PREFIX = "account:rest:"
WARMUP_LAST_PREFIX = "account:warmup:"
PAGES_PREFIX = "account:pages:"
PAGES_TTL_SECONDS = 48 * 3600
ACTIVITY_TTL_SECONDS = 30 * 86_400


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _pages_key(account_id: str, day: str | None = None) -> str:
    return f"{PAGES_PREFIX}{account_id}:{day or _today()}"


async def note_activity(redis: Redis, account_id: str, *, pages: int = 1) -> None:
    """Фиксирует активность аккаунта: последний раз и страницы за сегодня."""
    now = int(time.time())
    await redis.set(f"{LAST_ACTIVITY_PREFIX}{account_id}", now, ex=ACTIVITY_TTL_SECONDS)
    if pages > 0:
        key = _pages_key(account_id)
        await redis.incrby(key, pages)
        await redis.expire(key, PAGES_TTL_SECONDS)


async def pages_today(redis: Redis, account_id: str) -> int:
    value = await redis.get(_pages_key(account_id))
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


async def set_rest(redis: Redis, account_id: str, minutes: int, reason: str) -> int:
    """Отправляет аккаунт в «отдых» на N минут; возвращает timestamp окончания."""
    until = int(time.time()) + max(1, minutes) * 60
    await redis.set(f"{REST_UNTIL_PREFIX}{account_id}", until, ex=max(60, minutes * 60))
    await redis.set(
        f"{REST_UNTIL_PREFIX}{account_id}:reason", reason[:200], ex=max(60, minutes * 60)
    )
    return until


async def clear_rest(redis: Redis, account_id: str) -> None:
    await redis.delete(
        f"{REST_UNTIL_PREFIX}{account_id}", f"{REST_UNTIL_PREFIX}{account_id}:reason"
    )


async def rest_until(redis: Redis, account_id: str) -> int:
    value = await redis.get(f"{REST_UNTIL_PREFIX}{account_id}")
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


async def can_use(
    redis: Redis, account_id: str, *, daily_limit: int, rest_minutes: int
) -> tuple[bool, str | None]:
    """Можно ли сейчас работать аккаунтом. При превышении лимита — уводим в отдых."""
    until = await rest_until(redis, account_id)
    now = int(time.time())
    if until > now:
        minutes = (until - now) // 60 + 1
        reason = await redis.get(f"{REST_UNTIL_PREFIX}{account_id}:reason")
        text = reason.decode() if isinstance(reason, bytes) else reason
        return False, f"аккаунт отдыхает ещё ~{minutes} мин ({text or 'пауза'})"
    used = await pages_today(redis, account_id)
    if daily_limit > 0 and used >= daily_limit:
        await set_rest(redis, account_id, rest_minutes, f"дневной лимит {daily_limit} стр.")
        return False, f"дневной лимит {daily_limit} страниц исчерпан — отдых {rest_minutes} мин"
    return True, None


async def account_care_state(redis: Redis, account_id: str, *, daily_limit: int) -> dict[str, Any]:
    last_raw = await redis.get(f"{LAST_ACTIVITY_PREFIX}{account_id}")
    warm_raw = await redis.get(f"{WARMUP_LAST_PREFIX}{account_id}")
    until = await rest_until(redis, account_id)
    reason = await redis.get(f"{REST_UNTIL_PREFIX}{account_id}:reason")
    reason_text = reason.decode() if isinstance(reason, bytes) else reason

    def _iso(value: Any) -> str | None:
        try:
            return datetime.fromtimestamp(int(value), tz=UTC).isoformat()
        except (TypeError, ValueError):
            return None

    return {
        "pages_today": await pages_today(redis, account_id),
        "daily_limit": daily_limit,
        "last_activity": _iso(last_raw),
        "warmup_last": _iso(warm_raw),
        "rest_until": _iso(until) if until > int(time.time()) else None,
        "rest_reason": reason_text if until > int(time.time()) else None,
    }


async def mark_warmed(redis: Redis, account_id: str) -> None:
    await redis.set(f"{WARMUP_LAST_PREFIX}{account_id}", int(time.time()), ex=ACTIVITY_TTL_SECONDS)


async def warmup_due(redis: Redis, account_id: str, *, idle_hours: int) -> bool:
    """Пора ли прогреть: давно не было активности и аккаунт не отдыхает."""
    now = time.time()
    if await rest_until(redis, account_id) > now:
        return False
    warm_raw = await redis.get(f"{WARMUP_LAST_PREFIX}{account_id}")
    last_raw = await redis.get(f"{LAST_ACTIVITY_PREFIX}{account_id}")
    try:
        warm_ts = float(warm_raw) if warm_raw else 0.0
    except (TypeError, ValueError):
        warm_ts = 0.0
    try:
        last_ts = float(last_raw) if last_raw else 0.0
    except (TypeError, ValueError):
        last_ts = 0.0
    return now - max(warm_ts, last_ts) >= max(1, idle_hours) * 3600
