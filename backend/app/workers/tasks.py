import asyncio
import importlib.util
import logging
import uuid

import dramatiq
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.collectors.base import SourceAdapter
from app.collectors.ratelimit import RedisRateLimiter
from app.collectors.transport.http_cffi import HttpCffiTransport
from app.config import get_settings
from app.db.session import dispose_engine, get_engine
from app.services.collector import CrawlResult, SearchCollector

logger = logging.getLogger(__name__)

CRAWL_TIME_LIMIT_MS = 30 * 60 * 1000
HAS_BROWSER = importlib.util.find_spec("patchright") is not None


def _build_transport() -> SourceAdapter:
    http = HttpCffiTransport()
    if not HAS_BROWSER:
        logger.warning("patchright не установлен: Level 2 (браузер) отключён")
        return http
    from app.collectors.transport.browser_patchright import BrowserTransport
    from app.collectors.transport.hybrid import HybridTransport

    return HybridTransport(http, BrowserTransport())


async def _collect(search_id: str) -> CrawlResult:
    settings = get_settings()
    transport = _build_transport()
    redis = Redis.from_url(settings.redis_url)
    try:
        session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
        async with session_factory() as session:
            collector = SearchCollector(session, transport, RedisRateLimiter(redis))
            return await collector.collect(uuid.UUID(search_id))
    finally:
        await transport.close()
        await redis.aclose()
        await dispose_engine()


@dramatiq.actor(queue_name="crawl", max_retries=3, time_limit=CRAWL_TIME_LIMIT_MS)
def crawl_search(search_id: str) -> None:
    """Обход поиска: Level 1 (curl_cffi) → парсинг → снапшоты цен."""
    result = asyncio.run(_collect(search_id))
    logger.info("crawl finished: %s", result.to_dict())
