import asyncio
import time

from redis.asyncio import Redis

WINDOW_SECONDS = 60
WINDOW_TTL_SECONDS = 90


class RedisRateLimiter:
    """Ограничитель частоты на fixed-window счётчике в Redis.

    Ключ на минуту: ratelimit:{key}:{window}. При исчерпании квоты
    ждёт начала следующего окна, но не дольше timeout_seconds.
    """

    def __init__(self, redis: Redis, key_prefix: str = "ratelimit") -> None:
        self._redis = redis
        self._key_prefix = key_prefix

    def _bucket_key(self, key: str, window: int) -> str:
        return f"{self._key_prefix}:{key}:{window}"

    async def acquire(self, key: str, rate_per_minute: int, timeout_seconds: float = 60.0) -> None:
        if rate_per_minute <= 0:
            return
        deadline = time.monotonic() + timeout_seconds
        while True:
            window = int(time.time() // WINDOW_SECONDS)
            bucket = self._bucket_key(key, window)
            current = await self._redis.incr(bucket)
            if current == 1:
                await self._redis.expire(bucket, WINDOW_TTL_SECONDS)
            if current <= rate_per_minute:
                return
            seconds_left = WINDOW_SECONDS - int(time.time() % WINDOW_SECONDS)
            if time.monotonic() + seconds_left > deadline:
                raise TimeoutError(f"rate limit for {key} not available within timeout")
            await asyncio.sleep(seconds_left + 0.5)
