import asyncio
import importlib.util
import logging
import uuid
from datetime import date

import dramatiq
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.collectors.base import SourceAdapter
from app.collectors.ratelimit import RedisRateLimiter
from app.collectors.transport.http_cffi import HttpCffiTransport
from app.config import get_settings
from app.db.models import Search
from app.db.session import dispose_engine, get_engine
from app.integrations.avito_api.client import AvitoApiClient
from app.services.alerts import evaluate_search_alerts
from app.services.analytics.service import recalc_daily_analytics
from app.services.avito_sync import sync_our_listings
from app.services.collector import CrawlResult, SearchCollector
from app.services.matching import match_all_our_listings

logger = logging.getLogger(__name__)

CRAWL_TIME_LIMIT_MS = 30 * 60 * 1000
ANALYTICS_TIME_LIMIT_MS = 10 * 60 * 1000
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
            result = await collector.collect(uuid.UUID(search_id))
            await recalc_daily_analytics(session, result.search_id)
            await evaluate_search_alerts(session, result.search_id)
            await session.commit()
            return result
    finally:
        await transport.close()
        await redis.aclose()
        await dispose_engine()


async def _recalc(search_id: str, day_iso: str | None = None) -> date:
    day = date.fromisoformat(day_iso) if day_iso else None
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    try:
        async with session_factory() as session:
            calc_day = await recalc_daily_analytics(session, uuid.UUID(search_id), day)
            await session.commit()
            return calc_day
    finally:
        await dispose_engine()


@dramatiq.actor(queue_name="crawl", max_retries=3, time_limit=CRAWL_TIME_LIMIT_MS)
def crawl_search(search_id: str) -> None:
    """Обход поиска: Level 1 (curl_cffi) → парсинг → снапшоты цен → агрегаты."""
    result = asyncio.run(_collect(search_id))
    logger.info("crawl finished: %s", result.to_dict())


@dramatiq.actor(queue_name="analytics", max_retries=2, time_limit=ANALYTICS_TIME_LIMIT_MS)
def recalc_analytics(search_id: str, day_iso: str | None = None) -> None:
    """Пересчёт дневных агрегатов поиска (в том числе ночной догон)."""
    calc_day = asyncio.run(_recalc(search_id, day_iso))
    logger.info("analytics recalculated: search=%s day=%s", search_id, calc_day)


async def _sync_avito(match: bool) -> dict[str, int]:
    client = AvitoApiClient.from_settings()
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await sync_our_listings(session, client)
            matched = 0
            alerts_created = 0
            if match:
                matched = await match_all_our_listings(session)
                search_rows = await session.execute(
                    select(Search.id).where(Search.is_active.is_(True))
                )
                for (search_id,) in search_rows.all():
                    alerts_created += len(await evaluate_search_alerts(session, search_id))
                await session.commit()
            return {
                "created": result.created,
                "updated": result.updated,
                "skipped": result.skipped,
                "pages_fetched": result.pages_fetched,
                "matched": matched,
                "alerts_created": alerts_created,
            }
    finally:
        await client.close()
        await dispose_engine()


@dramatiq.actor(queue_name="avito", max_retries=2, time_limit=ANALYTICS_TIME_LIMIT_MS)
def sync_avito(match: bool = True) -> None:
    """Синхронизация своих объявлений с официальным API Avito."""
    counts = asyncio.run(_sync_avito(match))
    logger.info("avito sync finished: %s", counts)
