import asyncio
import importlib.util
import logging
import uuid
from datetime import date

import dramatiq
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collectors.base import SourceAdapter
from app.collectors.ratelimit import RedisRateLimiter
from app.collectors.transport.http_cffi import HttpCffiTransport
from app.config import get_settings
from app.db.models import OurListing, Search
from app.db.session import dispose_engine, get_engine
from app.services.alerts import evaluate_search_alerts
from app.services.analytics.service import recalc_daily_analytics
from app.services.collector import CrawlResult, SearchCollector
from app.services.matching import match_all_our_listings
from app.services.moderation import moderate_search
from app.services.progress import CrawlProgress

logger = logging.getLogger(__name__)

CRAWL_TIME_LIMIT_MS = 30 * 60 * 1000
ANALYTICS_TIME_LIMIT_MS = 10 * 60 * 1000
HAS_BROWSER = importlib.util.find_spec("patchright") is not None


def _build_transport() -> SourceAdapter:
    settings = get_settings()
    mode = settings.crawl_transport.strip().lower()
    http = HttpCffiTransport()
    if mode == "http":
        return http
    if not HAS_BROWSER:
        logger.warning("patchright не установлен: остаётся только HTTP (Level 1)")
        return http
    from app.collectors.transport.browser_patchright import BrowserTransport
    from app.collectors.transport.hybrid import HybridTransport

    browser = BrowserTransport()
    if mode == "hybrid":
        return HybridTransport(http, browser)
    return browser


async def _match_if_needed(session: AsyncSession) -> int:
    active_count = await session.scalar(
        select(func.count()).select_from(OurListing).where(OurListing.is_active.is_(True))
    )
    if not active_count:
        return 0
    return await match_all_our_listings(session)


async def _collect(search_id: str) -> CrawlResult:
    settings = get_settings()
    transport = _build_transport()
    redis = Redis.from_url(settings.redis_url)
    progress = CrawlProgress(redis, search_id)
    try:
        session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
        async with session_factory() as session:
            search = await session.get(Search, uuid.UUID(search_id))
            await progress.start(
                settings.crawl_max_pages_per_run,
                search.name if search is not None else None,
            )
            collector = SearchCollector(
                session, transport, RedisRateLimiter(redis), progress=progress
            )
            result = await collector.collect(uuid.UUID(search_id))
            await progress.stage("moderation")
            moderation = await moderate_search(
                session,
                result.search_id,
                transport=transport,
                with_descriptions=settings.moderation_descriptions_enabled,
            )
            await progress.stage("analytics")
            await recalc_daily_analytics(session, result.search_id)
            await progress.stage("matching")
            matched = await _match_if_needed(session)
            await progress.stage("alerts")
            await evaluate_search_alerts(session, result.search_id)
            await session.commit()
            await progress.finish(result.to_dict())
            logger.info(
                "crawl pipeline: matched %s our SKUs, flagged %s listings "
                "(categories %s, descriptions %s), ai-scored %s",
                matched,
                moderation.flagged,
                moderation.categories,
                moderation.described,
                moderation.ai_scored,
            )
            return result
    except Exception as error:
        await progress.fail(str(error))
        raise
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
