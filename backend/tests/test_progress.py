import uuid

import fakeredis.aioredis
import pytest

from app.services.progress import CrawlProgress, list_running_progress, read_progress


@pytest.fixture()
async def redis():
    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.aclose()


async def test_progress_lifecycle(redis) -> None:
    search_id = uuid.uuid4()
    progress = CrawlProgress(redis, search_id)

    await progress.start(max_pages=5, search_name="Тест")
    data = await read_progress(redis, search_id)
    assert data is not None
    assert data["status"] == "running"
    assert data["stage"] == "crawl"
    assert data["max_pages"] == 5
    assert data["search_name"] == "Тест"

    await progress.page(2, 80)
    data = await read_progress(redis, search_id)
    assert data is not None
    assert data["page"] == 2
    assert data["listings_seen"] == 80

    await progress.stage("matching")
    data = await read_progress(redis, search_id)
    assert data is not None
    assert data["stage"] == "matching"

    running = await list_running_progress(redis)
    assert len(running) == 1
    assert running[0]["search_id"] == str(search_id)

    await progress.finish({"pages_fetched": 5, "new_listings": 120})
    data = await read_progress(redis, search_id)
    assert data is not None
    assert data["status"] == "done"
    assert data["result"] == {"pages_fetched": 5, "new_listings": 120}
    assert await list_running_progress(redis) == []


async def test_progress_failure(redis) -> None:
    search_id = uuid.uuid4()
    progress = CrawlProgress(redis, search_id)
    await progress.start(max_pages=1)
    await progress.fail("bot challenge")
    data = await read_progress(redis, search_id)
    assert data is not None
    assert data["status"] == "failed"
    assert data["error"] == "bot challenge"


async def test_read_progress_missing(redis) -> None:
    assert await read_progress(redis, uuid.uuid4()) is None
