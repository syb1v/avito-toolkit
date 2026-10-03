import asyncio
import importlib.util
import logging
import random
import uuid
from datetime import UTC, date, datetime

import dramatiq
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collectors.base import SourceAdapter
from app.collectors.ratelimit import RedisRateLimiter
from app.collectors.transport.http_cffi import HttpCffiTransport
from app.collectors.web.parsing import parse_search_page
from app.config import get_settings
from app.db.models import AvitoAccount, OurListing, Search
from app.db.session import dispose_engine, get_engine
from app.services.accounts import account_for_search
from app.services.alerts import evaluate_search_alerts
from app.services.analytics.service import recalc_daily_analytics
from app.services.collector import CrawlResult, SearchCollector
from app.services.cookies import apply_cookies_to_profile, parse_cookie_input
from app.services.crawl_guard import CrawlGuard, classify_failure
from app.services.matching import match_all_our_listings
from app.services.moderation import moderate_search
from app.services.progress import CrawlProgress
from app.services.proxy_pool import build_proxy_pool
from app.services.regions import with_city

logger = logging.getLogger(__name__)

CRAWL_TIME_LIMIT_MS = 30 * 60 * 1000
ANALYTICS_TIME_LIMIT_MS = 10 * 60 * 1000
ACCOUNT_LOCK_TTL_SECONDS = 35 * 60
ACCOUNT_CHECK_URL = "https://www.avito.ru/all?q=iphone"
HAS_BROWSER = importlib.util.find_spec("patchright") is not None


def _build_transport(
    redis: Redis,
    *,
    user_data_dir: str | None = None,
    proxy_url: str | None = None,
) -> SourceAdapter:
    settings = get_settings()
    mode = settings.crawl_transport.strip().lower()
    # Закреплённый за аккаунтом прокси важнее общего пула: cookies+IP — одна связка.
    pool = None if proxy_url else build_proxy_pool(redis)
    http = HttpCffiTransport(proxy=proxy_url) if proxy_url else HttpCffiTransport(proxy_pool=pool)
    if mode == "http":
        return http
    if not HAS_BROWSER:
        logger.warning("patchright не установлен: остаётся только HTTP (Level 1)")
        return http
    from app.collectors.transport.browser_patchright import BrowserTransport
    from app.collectors.transport.hybrid import HybridTransport

    browser = BrowserTransport(
        proxy=proxy_url,
        proxy_pool=pool,
        block_resources=settings.browser_block_resources,
        user_data_dir=user_data_dir,
    )
    if mode == "hybrid":
        return HybridTransport(http, browser)
    return browser


def _empty_result(search_id: str) -> CrawlResult:
    return CrawlResult(
        search_id=uuid.UUID(search_id),
        pages_fetched=0,
        pages_failed=0,
        listings_seen=0,
        new_listings=0,
        price_changes=0,
        gone_listings=0,
    )


async def _match_if_needed(session: AsyncSession) -> int:
    active_count = await session.scalar(
        select(func.count()).select_from(OurListing).where(OurListing.is_active.is_(True))
    )
    if not active_count:
        return 0
    return await match_all_our_listings(session)


async def _collect(search_id: str) -> CrawlResult:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    progress = CrawlProgress(redis, search_id)
    guard = CrawlGuard(
        redis,
        min_interval_minutes=settings.crawl_min_interval_minutes,
        challenge_cooldown_minutes=settings.crawl_challenge_cooldown_minutes,
        rate_limit_cooldown_minutes=settings.crawl_rate_limit_cooldown_minutes,
        breaker_failures=settings.crawl_breaker_failures,
        breaker_minutes=settings.crawl_breaker_minutes,
    )
    transport: SourceAdapter | None = None
    account_lock_key: str | None = None
    try:
        session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
        async with session_factory() as session:
            search = await session.get(Search, uuid.UUID(search_id))
            if search is None:
                logger.warning("crawl skipped: search %s deleted", search_id)
                await progress.fail("поиск удалён")
                return _empty_result(search_id)
            account = await account_for_search(session, search)
            if account is not None and account.status != "active":
                reason = f"аккаунт «{account.name}» на паузе"
                logger.warning("crawl skipped for %s: %s", search_id, reason)
                await progress.stage("cooldown")
                await progress.finish({"skipped": True, "reason": reason})
                return _empty_result(search_id)
            if account is not None and account.role == "seller":
                reason = f"аккаунт «{account.name}» — продавец; для поиска привяжите «поисковика»"
                logger.warning("crawl skipped for %s: %s", search_id, reason)
                await progress.stage("cooldown")
                await progress.finish({"skipped": True, "reason": reason})
                return _empty_result(search_id)
            block_reason = await guard.block_reason(search_id)
            if block_reason is not None:
                logger.warning("crawl skipped for %s: %s", search_id, block_reason)
                await progress.stage("cooldown")
                await progress.finish({"skipped": True, "reason": block_reason})
                return _empty_result(search_id)
            if settings.worker_pause_max_seconds > 0:
                await progress.stage("pausing")
                await asyncio.sleep(
                    random.uniform(
                        settings.worker_pause_min_seconds,
                        max(settings.worker_pause_min_seconds, settings.worker_pause_max_seconds),
                    )
                )
            max_pages = settings.crawl_max_pages_per_run
            if isinstance(search.params, dict):
                override = search.params.get("max_pages")
                if (
                    isinstance(override, int)
                    and not isinstance(override, bool)
                    and 0 <= override <= 500
                ):
                    max_pages = override
            token = str(account.id) if account is not None else "default"
            account_lock_key = f"crawl:account-lock:{token}"
            locked = await redis.set(
                account_lock_key, search_id, nx=True, ex=ACCOUNT_LOCK_TTL_SECONDS
            )
            if not locked:
                reason = "профиль занят другим обходом"
                logger.warning("crawl skipped for %s: %s", search_id, reason)
                await progress.stage("cooldown")
                await progress.finish({"skipped": True, "reason": reason})
                return _empty_result(search_id)
            transport = _build_transport(
                redis,
                user_data_dir=account.profile_dir if account is not None else None,
                proxy_url=account.proxy_url if account is not None else None,
            )
            city = search.params.get("city") if isinstance(search.params, dict) else None
            url_override = with_city(search.url, city) if isinstance(city, str) else None
            await progress.start(max_pages, search.name)
            collector = SearchCollector(
                session,
                transport,
                RedisRateLimiter(redis),
                max_pages=max_pages,
                progress=progress,
                url_override=url_override,
            )
            result = await collector.collect(uuid.UUID(search_id))
            failure_reason = classify_failure(
                stopped_by_challenge=result.stopped_by_challenge,
                rate_limited=result.rate_limited,
                pages_failed=result.pages_failed,
                pages_fetched=result.pages_fetched,
            )
            if failure_reason is not None:
                await guard.note_failure(search_id, failure_reason)
            else:
                await guard.note_success(search_id)
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
        if account_lock_key is not None:
            await redis.delete(account_lock_key)
        if transport is not None:
            await transport.close()
        await redis.aclose()
        await dispose_engine()


async def _recalc(search_id: str, day_iso: str | None = None) -> date:
    day = date.fromisoformat(day_iso) if day_iso else None
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    try:
        async with session_factory() as session:
            if await session.get(Search, uuid.UUID(search_id)) is None:
                logger.warning("analytics skipped: search %s deleted", search_id)
                return day or date.today()
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


async def _check_proxies() -> dict[str, int]:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        pool = build_proxy_pool(redis, force=True)
        if pool is None:
            return {"checked": 0, "ok": 0, "failed": 0}
        return await pool.check_all()
    finally:
        await redis.aclose()


@dramatiq.actor(queue_name="proxy", max_retries=1, time_limit=ANALYTICS_TIME_LIMIT_MS)
def check_proxies() -> None:
    """Healthcheck всех прокси пула (статусы в Redis, видны в панели)."""
    result = asyncio.run(_check_proxies())
    logger.info("proxy healthcheck: %s", result)


async def _check_account(account_id: str) -> dict[str, object]:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    transport: SourceAdapter | None = None
    try:
        async with session_factory() as session:
            account = await session.get(AvitoAccount, uuid.UUID(account_id))
            if account is None:
                raise LookupError(f"account {account_id} not found")
            cooldown = settings.account_check_cooldown_minutes * 60
            if (
                cooldown > 0
                and account.last_check_at is not None
                and (datetime.now(UTC) - account.last_check_at).total_seconds() < cooldown
            ):
                return {"account_id": account_id, "skipped": "cooldown"}
            transport = _build_transport(
                redis,
                user_data_dir=account.profile_dir,
                proxy_url=account.proxy_url,
            )
            checked_at = datetime.now(UTC)
            try:
                page = await transport.fetch(ACCOUNT_CHECK_URL)
                items = len(parse_search_page(page.body, base_url=page.url))
                ok = page.status_code < 400 and items > 0
                account.last_check_ok = ok
                account.last_error = None if ok else f"HTTP {page.status_code}, items={items}"
                result: dict[str, object] = {
                    "account_id": account_id,
                    "ok": ok,
                    "status_code": page.status_code,
                    "items": items,
                }
            except Exception as error:  # noqa: BLE001 — статус фиксируем в БД
                account.last_check_ok = False
                account.last_error = f"{type(error).__name__}: {error}"
                result = {"account_id": account_id, "ok": False, "error": str(error)}
            account.last_check_at = checked_at
            if account.last_check_ok and account.status == "paused":
                account.status = "active"
            await session.commit()
            return result
    finally:
        if transport is not None:
            await transport.close()
        await redis.aclose()
        await dispose_engine()


@dramatiq.actor(queue_name="crawl", max_retries=1, time_limit=CRAWL_TIME_LIMIT_MS)
def check_account(account_id: str) -> None:
    """Проверка профиля аккаунта: Авито отдаёт выдачу через его cookies."""
    result = asyncio.run(_check_account(account_id))
    logger.info("account check: %s", result)


async def _apply_account_cookies(account_id: str, raw: str, fresh: bool) -> dict[str, object]:
    cookies = parse_cookie_input(raw)
    if not cookies:
        raise ValueError("cookies не найдены (нужны домены avito.ru)")
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    try:
        async with session_factory() as session:
            account = await session.get(AvitoAccount, uuid.UUID(account_id))
            if account is None:
                raise LookupError(f"account {account_id} not found")
            check = await apply_cookies_to_profile(cookies, account.profile_dir, fresh=fresh)
            now = datetime.now(UTC)
            account.cookies_at = now
            account.last_check_at = now
            account.last_check_ok = check.ok
            account.last_error = None if check.ok else f"проверка: объявлений={check.items}"
            if check.ok and account.status == "paused":
                account.status = "active"
            await session.commit()
            return {
                "account_id": account_id,
                "ok": check.ok,
                "items": check.items,
                "challenge": check.challenge,
            }
    finally:
        await dispose_engine()


@dramatiq.actor(queue_name="crawl", max_retries=1, time_limit=CRAWL_TIME_LIMIT_MS)
def apply_account_cookies(account_id: str, raw: str, fresh: bool = True) -> None:
    """Загрузка cookies в аккаунт из UI: пишет в профиль и проверяет выдачу."""
    result = asyncio.run(_apply_account_cookies(account_id, raw, fresh))
    logger.info("account cookies applied: %s", result)
