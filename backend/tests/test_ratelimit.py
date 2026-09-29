import fakeredis.aioredis
import pytest

from app.collectors.ratelimit import RedisRateLimiter


@pytest.fixture()
async def redis():
    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.aclose()


async def test_allows_requests_up_to_limit(redis) -> None:
    limiter = RedisRateLimiter(redis)
    await limiter.acquire("avito.ru", 2)
    await limiter.acquire("avito.ru", 2)


async def test_raises_when_window_exhausted(redis) -> None:
    limiter = RedisRateLimiter(redis)
    await limiter.acquire("avito.ru", 1)
    with pytest.raises(TimeoutError):
        await limiter.acquire("avito.ru", 1, timeout_seconds=0.1)


async def test_zero_rate_is_noop(redis) -> None:
    limiter = RedisRateLimiter(redis)
    await limiter.acquire("avito.ru", 0)


async def test_keys_are_isolated(redis) -> None:
    limiter = RedisRateLimiter(redis)
    await limiter.acquire("avito.ru", 1)
    await limiter.acquire("other.ru", 1)
