import time

import fakeredis.aioredis
import pytest

from app.services.queues import HEARTBEAT_KEY, queue_depth, worker_alive


@pytest.fixture()
async def redis():
    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.aclose()


async def test_queue_depth_missing_keys(redis) -> None:
    assert await queue_depth(redis, "dramatiq:crawl") == 0


async def test_queue_depth_counts_stream_and_delayed(redis) -> None:
    await redis.xadd("dramatiq:crawl.msgs", {"a": "1"})
    await redis.xadd("dramatiq:crawl.msgs", {"a": "2"})
    await redis.zadd("dramatiq:crawl.XQ", {"msg": 123})
    assert await queue_depth(redis, "dramatiq:crawl") == 3


async def test_worker_alive_by_heartbeat(redis) -> None:
    assert await worker_alive(redis, window_seconds=60) is False
    await redis.zadd(HEARTBEAT_KEY, {"worker": time.time()})
    assert await worker_alive(redis, window_seconds=60) is True
    await redis.zadd(HEARTBEAT_KEY, {"worker": time.time() - 3600})
    assert await worker_alive(redis, window_seconds=60) is False
