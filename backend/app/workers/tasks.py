import asyncio
import importlib.util
import json
import logging
import random
import time
import uuid
from datetime import UTC, date, datetime

import dramatiq
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.prompts import REPRICE_SUMMARY_VERSION
from app.ai.runs import record_llm_run
from app.ai.tasks import summarize_price_edits
from app.collectors.base import BotChallengeError, RateLimitedError, SourceAdapter
from app.collectors.ratelimit import RedisRateLimiter
from app.collectors.transport.http_cffi import HttpCffiTransport
from app.collectors.web.parsing import parse_search_page
from app.config import get_settings
from app.db.models import (
    Alert,
    AvitoAccount,
    Listing,
    ListingEdit,
    OurListing,
    Search,
    SearchListing,
)
from app.db.session import dispose_engine, get_engine
from app.services.account_care import (
    can_use,
    mark_warmed,
    note_activity,
    rest_until,
    set_rest,
)
from app.services.accounts import account_for_search, resolve_profile_path
from app.services.alerts import evaluate_search_alerts
from app.services.analytics.service import recalc_daily_analytics
from app.services.avito_api import (
    AvitoApiError,
    account_credentials,
    env_credentials,
    fetch_item_info,
    fetch_self,
    update_item_price,
)
from app.services.collector import CrawlResult, SearchCollector
from app.services.cookies import apply_cookies_to_profile, parse_cookie_input
from app.services.crawl_guard import CrawlGuard, classify_failure
from app.services.events import publish
from app.services.matching import match_all_our_listings
from app.services.moderation import enrich_descriptions, moderate_search
from app.services.progress import CrawlProgress
from app.services.proxy_pool import browser_proxy_url, build_proxy_pool
from app.services.recommendations import build_recommendations
from app.services.regions import with_city
from app.services.reprice import (
    get_auto_reprice_state,
    save_last_run,
    select_recommendations,
)
from app.services.seller import item_id_from_url

logger = logging.getLogger(__name__)

CRAWL_TIME_LIMIT_MS = 30 * 60 * 1000
ANALYTICS_TIME_LIMIT_MS = 10 * 60 * 1000
ACCOUNT_LOCK_TTL_SECONDS = 35 * 60
ACCOUNT_CHECK_URL = "https://www.avito.ru/all?q=iphone"
SELLER_PROFILE_URL = "https://www.avito.ru/profile"
HAS_BROWSER = importlib.util.find_spec("patchright") is not None


async def _build_transport(
    redis: Redis,
    session: AsyncSession,
    *,
    user_data_dir: str | None = None,
    proxy_url: str | None = None,
) -> SourceAdapter:
    settings = get_settings()
    mode = settings.crawl_transport.strip().lower()
    # Закреплённый за аккаунтом прокси важнее общего пула: cookies+IP — одна связка.
    # Браузер не умеет socks5 с авторизацией — берём HTTP-двойник, если он есть.
    browser_proxy = await browser_proxy_url(session, proxy_url)
    pool = None if proxy_url else await build_proxy_pool(redis, session)
    http = HttpCffiTransport(proxy=proxy_url) if proxy_url else HttpCffiTransport(proxy_pool=pool)
    if mode == "http":
        return http
    if not HAS_BROWSER:
        logger.warning("patchright не установлен: остаётся только HTTP (Level 1)")
        return http
    from app.collectors.transport.browser_patchright import BrowserTransport
    from app.collectors.transport.hybrid import HybridTransport

    browser = BrowserTransport(
        proxy=browser_proxy,
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


async def _fetch_descriptions(
    session: AsyncSession, search_id: uuid.UUID, transport: SourceAdapter
) -> int:
    """Догружает описания активных лотов поиска, чтобы фильтры видели и описание."""
    settings = get_settings()
    rows = await session.execute(
        select(Listing.id, Listing.url, Listing.description)
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .where(
            SearchListing.search_id == search_id,
            Listing.status == "active",
            Listing.url.is_not(None),
            Listing.description.is_(None),
        )
        .order_by(SearchListing.last_position.nulls_last())
        .limit(settings.crawl_descriptions_per_run)
    )
    candidates = [(int(row[0]), str(row[1]), row[2]) for row in rows.all()]
    if not candidates:
        return 0
    fetched = await enrich_descriptions(
        session,
        transport,
        candidates,
        max_items=settings.crawl_descriptions_per_run,
        delay_min=settings.moderation_description_delay_min_seconds,
        delay_max=settings.moderation_description_delay_max_seconds,
    )
    await session.commit()
    return fetched


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
            account_token = str(account.id) if account is not None else "default"
            allowed, care_reason = await can_use(
                redis,
                account_token,
                daily_limit=settings.account_daily_page_limit,
                rest_minutes=settings.account_rest_minutes,
            )
            if not allowed:
                logger.warning("crawl skipped for %s: %s", search_id, care_reason)
                await progress.stage("cooldown")
                await progress.finish({"skipped": True, "reason": care_reason})
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
            transport = await _build_transport(
                redis,
                session,
                user_data_dir=(
                    str(resolve_profile_path(account.profile_dir)) if account is not None else None
                ),
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
            await note_activity(redis, account_token, pages=max(0, result.pages_fetched))
            failure_reason = classify_failure(
                stopped_by_challenge=result.stopped_by_challenge,
                rate_limited=result.rate_limited,
                pages_failed=result.pages_failed,
                pages_fetched=result.pages_fetched,
            )
            if failure_reason is not None:
                await guard.note_failure(search_id, failure_reason)
                if failure_reason in ("challenge", "rate_limit"):
                    minutes = settings.account_rest_minutes
                    await set_rest(
                        redis,
                        account_token,
                        minutes,
                        (
                            "челлендж Авито"
                            if failure_reason == "challenge"
                            else "429: лимит запросов IP"
                        ),
                    )
            else:
                await guard.note_success(search_id)
            if settings.crawl_descriptions_per_run > 0:
                await progress.stage("descriptions")
                described = await _fetch_descriptions(session, result.search_id, transport)
            else:
                described = 0
            if settings.facets_ai_enabled:
                from app.services.facets import tag_search_listings

                tagged = await tag_search_listings(session, result.search_id)
                if tagged:
                    logger.info("facets: tagged %s listings", tagged)
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
            created_alerts = await evaluate_search_alerts(session, result.search_id)
            await session.commit()
            for alert in created_alerts:
                await publish(
                    redis,
                    "alert.new",
                    alert_id=str(alert.id),
                    alert_type=alert.type,
                    search_id=str(result.search_id),
                )
            payload = result.to_dict()
            payload["ai"] = {
                "scored": moderation.ai_scored,
                "desc_reviewed": moderation.desc_reviewed,
                "tokens_in": moderation.ai_tokens_in,
                "tokens_out": moderation.ai_tokens_out,
                "cost_usd": round(moderation.ai_cost_usd, 6),
            }
            await progress.finish(payload)
            logger.info(
                "crawl pipeline: descriptions +%s, matched %s our SKUs, flagged %s "
                "(categories %s, moderation descriptions %s), ai-scored %s",
                described,
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
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    try:
        async with session_factory() as session:
            pool = await build_proxy_pool(redis, session, force=True)
            if pool is None:
                return {"checked": 0, "ok": 0, "failed": 0}
            return await pool.check_all()
    finally:
        await redis.aclose()
        await dispose_engine()


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
            transport = await _build_transport(
                redis,
                session,
                user_data_dir=str(resolve_profile_path(account.profile_dir)),
                proxy_url=account.proxy_url,
            )
            check_url = ACCOUNT_CHECK_URL
            own_search_url = await session.scalar(
                select(Search.url)
                .where(Search.account_id == account.id, Search.is_active.is_(True))
                .order_by(Search.priority)
                .limit(1)
            )
            if own_search_url:
                check_url = own_search_url
            checked_at = datetime.now(UTC)
            rest_reason: str | None = None
            try:
                page = await transport.fetch(check_url)
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
            except RateLimitedError as error:
                account.last_check_ok = False
                account.last_error = (
                    "429: Авито лимитирует запросы (похоже на лимит IP, аккаунт не заблокирован)"
                )
                result = {
                    "account_id": account_id,
                    "ok": False,
                    "rate_limited": True,
                    "error": str(error),
                }
                rest_reason = "проверка: лимит запросов IP (не бан аккаунта)"
            except BotChallengeError as error:
                account.last_check_ok = False
                account.last_error = f"челлендж Авито — нужны свежие cookies ({error})"
                result = {
                    "account_id": account_id,
                    "ok": False,
                    "challenge": True,
                    "error": str(error),
                }
                rest_reason = "проверка: челлендж Авито"
            except Exception as error:  # noqa: BLE001 — статус фиксируем в БД
                account.last_check_ok = False
                account.last_error = f"{type(error).__name__}: {error}"
                result = {"account_id": account_id, "ok": False, "error": str(error)}
            await note_activity(redis, account_id, pages=1)
            if rest_reason is not None:
                await set_rest(redis, account_id, settings.account_rest_minutes, rest_reason)
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


async def _pick_seller_account(
    session: AsyncSession, account_id: uuid.UUID | None
) -> AvitoAccount | None:
    if account_id is not None:
        account = await session.get(AvitoAccount, account_id)
        if account is not None and account.role == "seller":
            return account
    return await session.scalar(
        select(AvitoAccount)
        .where(AvitoAccount.role == "seller", AvitoAccount.status == "active")
        .order_by(AvitoAccount.created_at)
        .limit(1)
    )


async def _apply_listing_edit(edit_id: str, revert: bool) -> dict[str, object]:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    try:
        async with session_factory() as session:
            edit = await session.get(ListingEdit, uuid.UUID(edit_id))
            if edit is None:
                return {"skipped": "edit not found"}
            our = await session.get(OurListing, edit.sku)
            if our is None:
                edit.status = "failed"
                edit.error = "наш SKU не найден"
                await session.commit()
                return {"ok": False, "error": edit.error}
            target = float(edit.old_price if revert else edit.target_price)
            if settings.seller_edit_mode != "live":
                edit.mode = "dry_run"
                edit.status = "reverted" if revert else "applied"
                edit.error = None
                now = datetime.now(UTC)
                if revert:
                    edit.reverted_at = now
                else:
                    edit.applied_at = now
                await session.commit()
                return {"ok": True, "mode": "dry_run", "target": target}

            account = await _pick_seller_account(session, edit.account_id)
            item_id = our.avito_item_id or item_id_from_url(our.avito_url)
            if item_id is None:
                edit.status = "failed"
                edit.error = "у SKU нет ID объявления Авито (импортируйте товары из файла/API)"
                await session.commit()
                return {"ok": False, "error": edit.error}
            credentials = (
                account_credentials(account) if account is not None else None
            ) or env_credentials(settings)
            if credentials is None:
                edit.status = "failed"
                edit.error = (
                    "у аккаунта-продавца нет API-ключей — добавьте client_id/secret "
                    "в «Аккаунтах» или задайте AVITO_CLIENT_ID/SECRET"
                )
                await session.commit()
                return {"ok": False, "error": edit.error}
            try:
                await update_item_price(redis, settings, item_id, target, credentials)
            except AvitoApiError as error:
                edit.status = "failed"
                edit.error = f"API Авито: {error.message}"
                await session.commit()
                await publish(
                    redis,
                    "edit.updated",
                    edit_id=str(edit.id),
                    sku=edit.sku,
                    status="failed",
                    error=edit.error,
                )
                return {"ok": False, "error": edit.error}
            edit.mode = "live"
            edit.status = "reverted" if revert else "applied"
            edit.error = None
            now = datetime.now(UTC)
            if revert:
                edit.reverted_at = now
            else:
                edit.applied_at = now
            our.price = target
            await session.commit()
            await publish(
                redis,
                "edit.updated",
                edit_id=str(edit.id),
                sku=edit.sku,
                status=edit.status,
                target_price=target,
            )
            logger.info("listing edit %s via API: %s", edit.id, target)
            return {
                "ok": True,
                "mode": "api",
                "message": f"цена обновлена через API: {int(round(target))} ₽",
            }
    finally:
        await redis.aclose()
        await dispose_engine()


@dramatiq.actor(queue_name="crawl", max_retries=1, time_limit=CRAWL_TIME_LIMIT_MS)
def apply_listing_edit(edit_id: str, revert: bool = False) -> None:
    """Правка цены объявления через кабинет продавца (dry-run или live)."""
    result = asyncio.run(_apply_listing_edit(edit_id, revert))
    logger.info("listing edit applied: %s", result)


WARMUP_URL = "https://www.avito.ru/"


async def _warmup_account(account_id: str) -> dict[str, object]:
    """Мягкий прогрев: главная + одна выдача аккаунта, с человеческими паузами."""
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    transport: SourceAdapter | None = None
    lock_key: str | None = None
    try:
        async with session_factory() as session:
            account = await session.get(AvitoAccount, uuid.UUID(account_id))
            if account is None or account.status != "active":
                return {"skipped": "account missing or paused"}
            if await rest_until(redis, account_id) > time.time():
                return {"skipped": "resting"}
            lock_key = f"crawl:account-lock:{account.id}"
            if not await redis.set(
                lock_key, f"warmup:{account.id}", nx=True, ex=ACCOUNT_LOCK_TTL_SECONDS
            ):
                return {"skipped": "busy"}
            transport = await _build_transport(
                redis,
                session,
                user_data_dir=str(resolve_profile_path(account.profile_dir)),
                proxy_url=account.proxy_url,
            )
            ok = True
            error_text: str | None = None
            try:
                if account.role == "seller":
                    await transport.fetch(SELLER_PROFILE_URL, expect_items=False)
                    await asyncio.sleep(random.uniform(3.0, 6.0))
                await transport.fetch(WARMUP_URL, expect_items=False)
                await asyncio.sleep(random.uniform(3.0, 6.0))
                search = await session.scalar(
                    select(Search)
                    .where(Search.account_id == account.id, Search.is_active.is_(True))
                    .order_by(Search.priority)
                    .limit(1)
                )
                if search is not None:
                    await transport.fetch(search.url, expect_items=False)
                    await asyncio.sleep(random.uniform(2.0, 5.0))
            except RateLimitedError:
                ok = False
                error_text = "прогрев: 429 — лимит запросов IP (аккаунт не заблокирован)"
                await set_rest(
                    redis,
                    account_id,
                    settings.account_rest_minutes,
                    "прогрев: лимит запросов IP (не бан аккаунта)",
                )
            except BotChallengeError as error:
                ok = False
                error_text = f"прогрев: челлендж Авито — обновите cookies ({error})"
                await set_rest(
                    redis,
                    account_id,
                    settings.account_rest_minutes,
                    "прогрев: челлендж Авито",
                )
            except Exception as error:  # noqa: BLE001 — фиксируем и продолжаем жить
                ok = False
                error_text = f"прогрев: {type(error).__name__}: {error}"
            if ok:
                await note_activity(redis, account_id, pages=2)
                await mark_warmed(redis, account_id)
            account.last_check_at = datetime.now(UTC)
            account.last_check_ok = ok
            account.last_error = error_text
            await session.commit()
            return {"account_id": account_id, "ok": ok, "error": error_text}
    finally:
        if lock_key is not None:
            await redis.delete(lock_key)
        if transport is not None:
            await transport.close()
        await redis.aclose()
        await dispose_engine()


@dramatiq.actor(queue_name="crawl", max_retries=1, time_limit=ANALYTICS_TIME_LIMIT_MS)
def warmup_account(account_id: str) -> None:
    """Прогрев аккаунта: аккуратные заходы, чтобы сессия выглядела живой."""
    result = asyncio.run(_warmup_account(account_id))
    logger.info("account warmup: %s", result)


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
            check = await apply_cookies_to_profile(
                cookies,
                str(resolve_profile_path(account.profile_dir)),
                fresh=fresh,
                proxy_url=account.proxy_url,
            )
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


SYNC_KEY = "account-sync:{account_id}"
SYNC_TTL_SECONDS = 3600


def _extract_price(info: dict[str, object]) -> float | None:
    price = info.get("price")
    if isinstance(price, (int, float)):
        return float(price)
    if isinstance(price, dict):
        for key in ("value", "amount"):
            value = price.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    return None


async def _sync_account_items(account_id: str) -> dict[str, object]:
    """Обновляет цены/статусы наших SKU аккаунта через официальный API."""
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    key = SYNC_KEY.format(account_id=account_id)
    try:
        async with session_factory() as session:
            account = await session.get(AvitoAccount, uuid.UUID(account_id))
            if account is None:
                raise LookupError(f"account {account_id} not found")
            await redis.set(key, json.dumps({"status": "running"}), ex=SYNC_TTL_SECONDS)
            credentials = account_credentials(account)
            if credentials is None:
                raise RuntimeError("у аккаунта нет API-ключей — добавьте client_id/secret")
            user_id = account.api_user_id
            if user_id is None:
                me = await fetch_self(redis, settings, credentials)
                raw_id = me.get("id")
                if not isinstance(raw_id, int):
                    raise RuntimeError("API не вернул user id")
                user_id = raw_id
                account.api_user_id = user_id
            rows = (
                (
                    await session.execute(
                        select(OurListing).where(
                            OurListing.account == account.name,
                            OurListing.avito_item_id.is_not(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            updated = failed = 0
            items: list[dict[str, object]] = []
            for listing in rows:
                item_id = int(listing.avito_item_id or 0)
                if item_id <= 0:
                    continue
                try:
                    info = await fetch_item_info(redis, settings, credentials, user_id, item_id)
                except AvitoApiError as error:
                    failed += 1
                    items.append({"sku": listing.sku, "error": error.message})
                    continue
                new_price = _extract_price(info)
                status = info.get("status")
                changed = False
                if new_price is not None and float(listing.price) != new_price:
                    listing.price = new_price
                    changed = True
                if isinstance(status, str) and status and listing.avito_status != status:
                    listing.avito_status = status
                    changed = True
                if changed:
                    updated += 1
                items.append(
                    {
                        "sku": listing.sku,
                        "price": float(listing.price),
                        "status": listing.avito_status,
                    }
                )
            await session.commit()
            payload: dict[str, object] = {
                "status": "done",
                "total": len(rows),
                "updated": updated,
                "failed": failed,
                "items": items[:200],
            }
            await redis.set(key, json.dumps(payload, ensure_ascii=False), ex=SYNC_TTL_SECONDS)
            await publish(
                redis,
                "sync.done",
                account_id=account_id,
                total=payload["total"],
                updated=payload["updated"],
                failed=payload["failed"],
            )
            return payload
    except Exception as error:
        await redis.set(
            key,
            json.dumps(
                {"status": "error", "error": f"{type(error).__name__}: {error}"},
                ensure_ascii=False,
            ),
            ex=SYNC_TTL_SECONDS,
        )
        raise
    finally:
        await redis.aclose()
        await dispose_engine()


@dramatiq.actor(queue_name="analytics", max_retries=1, time_limit=ANALYTICS_TIME_LIMIT_MS)
def sync_account_items(account_id: str) -> None:
    """Синхронизирует наши SKU аккаунта через официальный API."""
    asyncio.run(_sync_account_items(account_id))


async def _auto_reprice() -> dict[str, object]:
    """Ночной прогон авто-правок: рекомендации → черновики/применение → AI-сводка."""
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    try:
        state = await get_auto_reprice_state(redis, settings)
        if not state.enabled:
            return {"skipped": "auto-reprice disabled"}
        effective_live = state.live and settings.seller_edit_mode == "live"
        mode = "live" if effective_live else "dry_run"
        async with session_factory() as session:
            recommendations = await build_recommendations(session)
            recommendations_by_sku = {item.sku: item for item in recommendations}
            our_rows = await session.execute(
                select(OurListing.sku, OurListing.avito_item_id, OurListing.avito_url).where(
                    OurListing.is_active.is_(True)
                )
            )
            active_skus = {row[0]: (row[1], row[2]) for row in our_rows.all()}
            busy_rows = await session.execute(
                select(ListingEdit.sku).where(
                    ListingEdit.status.in_(("draft", "approved", "applying", "reverting"))
                )
            )
            busy_skus = {row[0] for row in busy_rows.all()}
            selected = select_recommendations(
                recommendations, busy_skus=busy_skus, active_skus=active_skus
            )
            created: list[ListingEdit] = []
            for recommendation in selected:
                edit = ListingEdit(
                    sku=recommendation.sku,
                    old_price=recommendation.our_price,
                    target_price=recommendation.clamped_price,
                    delta_pct=recommendation.delta_pct,
                    strategy=recommendation.strategy,
                    status="draft" if recommendation.requires_approval else "approved",
                    mode=mode,
                )
                session.add(edit)
                created.append(edit)
            await session.commit()
            for edit in created:
                await session.refresh(edit)
            headline = ""
            if (
                created
                and settings.reprice_summary_enabled
                and settings.deepseek_api_key
                and settings.llm_model.startswith("deepseek/")
            ):
                items = []
                for edit in created:
                    recommendation = recommendations_by_sku[edit.sku]
                    items.append(
                        (
                            edit.sku,
                            recommendation.title,
                            float(edit.old_price),
                            float(edit.target_price),
                            edit.strategy,
                            recommendation.market_median,
                            recommendation.market_p25,
                            recommendation.market_p75,
                            recommendation.matched_count,
                        )
                    )
                try:
                    summary = await summarize_price_edits(items=items)
                except Exception as error:  # noqa: BLE001 — сводка не критична
                    logger.warning("reprice summary failed: %s", error)
                else:
                    await record_llm_run(
                        session,
                        task="reprice_summary",
                        result=summary,
                        prompt_version=REPRICE_SUMMARY_VERSION,
                    )
                    reasons = {item.sku: item.reason for item in summary.content.items}
                    headline = summary.content.headline
                    for edit in created:
                        edit.ai_summary = reasons.get(edit.sku)
                    await session.commit()
            applied = failed = 0
            item_payload = []
            for edit in created:
                status = edit.status
                if status == "approved":
                    try:
                        outcome = await _apply_listing_edit(str(edit.id), False)
                    except Exception as error:  # noqa: BLE001 — фиксируем и едем дальше
                        logger.warning("auto apply %s failed: %s", edit.sku, error)
                        failed += 1
                    else:
                        if outcome.get("ok"):
                            applied += 1
                        else:
                            failed += 1
                    await session.refresh(edit)
                    await asyncio.sleep(random.uniform(2.0, 5.0))
                item_payload.append(
                    {
                        "sku": edit.sku,
                        "old_price": float(edit.old_price),
                        "target_price": float(edit.target_price),
                        "delta_pct": round(edit.delta_pct, 2),
                        "status": edit.status,
                        "mode": edit.mode,
                        "reason": edit.ai_summary,
                    }
                )
            payload: dict[str, object] = {
                "at": datetime.now(UTC).isoformat(),
                "mode": mode,
                "created": len(created),
                "applied": applied,
                "failed": failed,
                "drafts": sum(1 for edit in created if edit.status == "draft"),
                "headline": headline,
                "items": item_payload,
            }
            if created:
                session.add(
                    Alert(
                        type="auto_reprice",
                        payload={
                            "kind": "auto_reprice",
                            "title": headline or "Ночной прогон авто-правок",
                            "mode": mode,
                            "created": len(created),
                            "applied": applied,
                            "drafts": payload["drafts"],
                            "failed": failed,
                        },
                        status="new",
                    )
                )
                await session.commit()
            await save_last_run(redis, payload)
            logger.info(
                "auto-reprice done: %s",
                {k: payload[k] for k in ("created", "applied", "drafts", "failed")},
            )
            return payload
    finally:
        await redis.aclose()
        await dispose_engine()


@dramatiq.actor(queue_name="analytics", max_retries=1, time_limit=ANALYTICS_TIME_LIMIT_MS)
def auto_reprice() -> None:
    """Ночной прогон авто-правок цен."""
    asyncio.run(_auto_reprice())
