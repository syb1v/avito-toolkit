import time

import fakeredis.aioredis
import pytest

from app.services.account_care import (
    can_use,
    clear_rest,
    mark_warmed,
    note_activity,
    pages_today,
    set_rest,
    warmup_due,
)


@pytest.fixture()
async def redis():
    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.aclose()


async def test_activity_counter_and_daily_limit(redis) -> None:
    await note_activity(redis, "a1", pages=3)
    assert await pages_today(redis, "a1") == 3
    ok, reason = await can_use(redis, "a1", daily_limit=5, rest_minutes=60)
    assert ok is True and reason is None

    await note_activity(redis, "a1", pages=2)
    ok, reason = await can_use(redis, "a1", daily_limit=5, rest_minutes=60)
    assert ok is False
    assert "лимит" in (reason or "")


async def test_manual_rest_and_resume(redis) -> None:
    until = await set_rest(redis, "a2", 30, "вручную")
    assert until > time.time()
    ok, reason = await can_use(redis, "a2", daily_limit=10, rest_minutes=60)
    assert ok is False
    assert "отдыхает" in (reason or "")

    await clear_rest(redis, "a2")
    ok, _ = await can_use(redis, "a2", daily_limit=10, rest_minutes=60)
    assert ok is True


async def test_warmup_due(redis) -> None:
    assert await warmup_due(redis, "a3", idle_hours=12) is True
    await mark_warmed(redis, "a3")
    assert await warmup_due(redis, "a3", idle_hours=12) is False
    await note_activity(redis, "a3", pages=1)
    assert await warmup_due(redis, "a3", idle_hours=12) is False
    await set_rest(redis, "a3", 10, "пауза")
    assert await warmup_due(redis, "a3", idle_hours=0) is False
