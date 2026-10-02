import uuid

import fakeredis.aioredis
import pytest

from app.services.crawl_guard import (
    REASON_CHALLENGE,
    REASON_NETWORK,
    REASON_RATE_LIMIT,
    CrawlGuard,
    classify_failure,
)


@pytest.fixture()
async def redis():
    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.aclose()


async def test_cooldown_blocks_after_failure(redis) -> None:
    guard = CrawlGuard(redis, challenge_cooldown_minutes=10, breaker_failures=5)
    search_id = uuid.uuid4()
    assert await guard.block_reason(search_id) is None
    await guard.note_failure(search_id, REASON_CHALLENGE)
    reason = await guard.block_reason(search_id)
    assert reason is not None
    assert "кулдаун" in reason


async def test_min_interval_blocks_after_success(redis) -> None:
    guard = CrawlGuard(redis, min_interval_minutes=30)
    search_id = uuid.uuid4()
    await guard.note_success(search_id)
    reason = await guard.block_reason(search_id)
    assert reason is not None
    assert "недавно обходили" in reason


async def test_circuit_breaker_trips_after_streak(redis) -> None:
    guard = CrawlGuard(redis, breaker_failures=2, breaker_minutes=5, challenge_cooldown_minutes=1)
    await guard.note_failure(uuid.uuid4(), REASON_RATE_LIMIT)
    await guard.note_failure(uuid.uuid4(), REASON_RATE_LIMIT)
    reason = await guard.block_reason(uuid.uuid4())
    assert reason is not None
    assert "серии блокировок" in reason


async def test_success_resets_streak(redis) -> None:
    guard = CrawlGuard(redis, breaker_failures=2)
    search_id = uuid.uuid4()
    await guard.note_failure(search_id, REASON_CHALLENGE)
    await guard.note_success(uuid.uuid4())
    state = await guard.state()
    assert state["fail_streak"] == 0


def test_classify_failure() -> None:
    assert (
        classify_failure(stopped_by_challenge=True, pages_failed=0, pages_fetched=1)
        == REASON_CHALLENGE
    )
    assert (
        classify_failure(stopped_by_challenge=False, pages_failed=1, pages_fetched=0)
        == REASON_NETWORK
    )
    assert (
        classify_failure(
            stopped_by_challenge=False,
            rate_limited=True,
            pages_failed=0,
            pages_fetched=0,
        )
        == REASON_RATE_LIMIT
    )
    assert classify_failure(stopped_by_challenge=False, pages_failed=0, pages_fetched=3) is None
