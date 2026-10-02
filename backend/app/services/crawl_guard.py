"""Защита от самоизбиения: кулдауны по поиску и глобальный circuit breaker."""

import logging
import uuid
from typing import Any

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

COOLDOWN_PREFIX = "crawl:cooldown:"
LAST_OK_PREFIX = "crawl:last_ok:"
FAIL_STREAK_KEY = "crawl:fail_streak"
BREAKER_UNTIL_KEY = "crawl:breaker_until"

REASON_CHALLENGE = "challenge"
REASON_RATE_LIMIT = "rate_limit"
REASON_NETWORK = "network"


class CrawlGuard:
    """Не даёт воркеру долбить Авито после блокировок и слишком часто по поиску."""

    def __init__(
        self,
        redis: Redis,
        *,
        min_interval_minutes: int = 30,
        challenge_cooldown_minutes: int = 60,
        rate_limit_cooldown_minutes: int = 90,
        breaker_failures: int = 3,
        breaker_minutes: int = 120,
    ) -> None:
        self._redis = redis
        self._min_interval = max(0, min_interval_minutes) * 60
        self._cooldowns = {
            REASON_CHALLENGE: max(1, challenge_cooldown_minutes) * 60,
            REASON_RATE_LIMIT: max(1, rate_limit_cooldown_minutes) * 60,
            REASON_NETWORK: max(1, challenge_cooldown_minutes) * 60,
        }
        self._breaker_failures = max(1, breaker_failures)
        self._breaker_minutes = max(1, breaker_minutes) * 60

    async def block_reason(self, search_id: uuid.UUID | str) -> str | None:
        breaker_ttl = await self._redis.ttl(BREAKER_UNTIL_KEY)
        if breaker_ttl and breaker_ttl > 0:
            return f"пауза после серии блокировок, ещё {breaker_ttl // 60} мин"
        cooldown_key = f"{COOLDOWN_PREFIX}{search_id}"
        cooldown_ttl = await self._redis.ttl(cooldown_key)
        if cooldown_ttl and cooldown_ttl > 0:
            reason = await self._redis.get(cooldown_key)
            reason_text = reason.decode() if isinstance(reason, bytes) else reason
            return f"кулдаун ({reason_text or 'блокировка'}), ещё {cooldown_ttl // 60} мин"
        if self._min_interval > 0:
            last_ok_key = f"{LAST_OK_PREFIX}{search_id}"
            last_ok_ttl = await self._redis.ttl(last_ok_key)
            if last_ok_ttl and last_ok_ttl > 0:
                seconds_left = last_ok_ttl
                if seconds_left > 0:
                    return f"недавно обходили, следующий через {seconds_left // 60} мин"
        return None

    async def note_success(self, search_id: uuid.UUID | str) -> None:
        await self._redis.set(f"{LAST_OK_PREFIX}{search_id}", "1", ex=self._min_interval or 1)
        await self._redis.delete(FAIL_STREAK_KEY)

    async def note_failure(self, search_id: uuid.UUID | str, reason: str) -> None:
        cooldown = self._cooldowns.get(reason, self._cooldowns[REASON_CHALLENGE])
        await self._redis.set(f"{COOLDOWN_PREFIX}{search_id}", reason, ex=cooldown)
        streak = await self._redis.incr(FAIL_STREAK_KEY)
        if streak == 1:
            await self._redis.expire(FAIL_STREAK_KEY, self._breaker_minutes)
        if streak >= self._breaker_failures:
            await self._redis.set(BREAKER_UNTIL_KEY, "1", ex=self._breaker_minutes)
            logger.error(
                "circuit breaker ON: %s фейлов подряд, пауза %s мин",
                streak,
                self._breaker_minutes // 60,
            )

    async def state(self) -> dict[str, Any]:
        return {
            "breaker_ttl": max(0, await self._redis.ttl(BREAKER_UNTIL_KEY) or 0),
            "fail_streak": int(await self._redis.get(FAIL_STREAK_KEY) or 0),
        }


def classify_failure(
    *,
    stopped_by_challenge: bool,
    pages_failed: int,
    pages_fetched: int,
    rate_limited: bool = False,
) -> str | None:
    if stopped_by_challenge:
        return REASON_CHALLENGE
    if rate_limited:
        return REASON_RATE_LIMIT
    if pages_failed > 0 and pages_fetched == 0:
        return REASON_NETWORK
    return None
