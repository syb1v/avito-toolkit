import asyncio
import logging
from datetime import UTC, datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from redis.asyncio import Redis
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Search
from app.db.session import dispose_engine, get_session_factory
from app.services.progress import CrawlProgress
from app.workers.tasks import check_proxies, crawl_search, recalc_analytics

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_SECONDS = 300
SEARCH_JOB_PREFIX = "search:"
ANALYTICS_HOUR_UTC = 1
ANALYTICS_MINUTE_UTC = 10


def _mark_queued(search_id: str) -> None:
    async def _write() -> None:
        settings = get_settings()
        redis = Redis.from_url(settings.redis_url)
        try:
            await CrawlProgress(redis, search_id).queued()
        finally:
            await redis.aclose()

    try:
        asyncio.run(_write())
    except Exception:
        logger.exception("failed to mark search %s as queued", search_id)


def _enqueue_search(search_id: str) -> None:
    crawl_search.send(search_id)
    _mark_queued(search_id)
    logger.info("enqueued crawl for search %s", search_id)


def _enqueue_analytics() -> None:
    try:
        searches = _load_searches()
    except Exception:
        logger.exception("failed to load searches for analytics")
        return
    for search_id, _ in searches:
        recalc_analytics.send(search_id)
    logger.info("enqueued daily analytics for %s searches", len(searches))


def _enqueue_proxy_check() -> None:
    check_proxies.send()
    logger.info("enqueued proxy healthcheck")


def _load_searches() -> list[tuple[str, str]]:
    async def _load() -> list[tuple[str, str]]:
        session_factory = get_session_factory()
        try:
            async with session_factory() as session:
                rows = await session.execute(
                    select(Search.id, Search.schedule_cron).where(Search.is_active.is_(True))
                )
                return [(str(row[0]), row[1]) for row in rows.all()]
        finally:
            await dispose_engine()

    return asyncio.run(_load())


def _refresh_jobs(scheduler: BlockingScheduler) -> None:
    for job in scheduler.get_jobs():
        if job.id.startswith(SEARCH_JOB_PREFIX):
            scheduler.remove_job(job.id)
    try:
        searches = _load_searches()
    except Exception:
        logger.exception("failed to load searches for scheduling")
        return
    scheduled = 0
    for search_id, cron in searches:
        try:
            trigger = CronTrigger.from_crontab(cron, timezone="UTC")
        except ValueError:
            logger.warning("invalid cron %r for search %s", cron, search_id)
            continue
        scheduler.add_job(
            _enqueue_search,
            trigger,
            args=[search_id],
            id=f"{SEARCH_JOB_PREFIX}{search_id}",
            replace_existing=True,
        )
        scheduled += 1
    logger.info("scheduler refreshed: %s searches scheduled", scheduled)


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        _refresh_jobs,
        "interval",
        seconds=REFRESH_INTERVAL_SECONDS,
        args=[scheduler],
        id="refresh",
        next_run_time=datetime.now(UTC),
    )
    scheduler.add_job(
        _enqueue_analytics,
        CronTrigger(hour=ANALYTICS_HOUR_UTC, minute=ANALYTICS_MINUTE_UTC, timezone="UTC"),
        id="analytics-daily",
    )
    has_proxies = bool(settings.proxy_list.strip()) or (
        settings.proxy_enabled and settings.proxy_url
    )
    if has_proxies and settings.proxy_healthcheck_enabled:
        scheduler.add_job(
            _enqueue_proxy_check,
            "interval",
            minutes=settings.proxy_healthcheck_interval_minutes,
            id="proxies-healthcheck",
        )
        logger.info(
            "proxy healthcheck scheduled every %s min",
            settings.proxy_healthcheck_interval_minutes,
        )
    logger.info("scheduler started")
    scheduler.start()


if __name__ == "__main__":
    main()
