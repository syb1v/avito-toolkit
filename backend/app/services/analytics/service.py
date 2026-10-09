import uuid
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Listing,
    ListingExclusion,
    MarketAnalyticsDaily,
    Search,
    SearchListing,
    Seller,
)
from app.services.analytics.aggregates import MarketSummary, build_market_summary
from app.services.analytics.iqr import compute_price_stats
from app.services.regions import (
    exclude_regions_from_params,
    matches_region,
    regions_from_params,
)
from app.services.search_filter import (
    combined_text,
    desc_verdict_ok,
    exclude_keywords_from_params,
    first_matching_exclude,
    keywords_from_params,
    matches_keyword_groups,
)
from app.services.seller_filter import (
    EXCLUDE_KEY,
    TARGET_KEY,
    seller_filter_reason,
    seller_refs_from_params,
)

LIFETIME_WINDOW_DAYS = 30
SUMMARY_HISTORY_DAYS = 30


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


@dataclass(frozen=True, slots=True)
class ExclusionCounts:
    keyword: int = 0
    stopword: int = 0
    region: int = 0
    manual: int = 0
    seller: int = 0


@dataclass(frozen=True, slots=True)
class FilteredListing:
    title: str
    price: float
    # None — объявление проходит фильтры; иначе причина исключения.
    reason: str | None = None


async def _filtered_listings(session: AsyncSession, search_id: uuid.UUID) -> list[FilteredListing]:
    """Активные объявления поиска (без флагов) с причиной исключения фильтрами."""
    search = await session.get(Search, search_id)
    params = search.params if search is not None else None
    groups = keywords_from_params(params)
    excludes = exclude_keywords_from_params(params)
    regions = regions_from_params(params)
    exclude_regions = exclude_regions_from_params(params)
    target_refs = seller_refs_from_params(params, TARGET_KEY)
    exclude_refs = seller_refs_from_params(params, EXCLUDE_KEY)
    max_age_days = params.get("max_age_days") if isinstance(params, dict) else None
    statement = (
        select(
            Listing.title,
            Listing.current_price,
            Listing.region,
            ListingExclusion.listing_id,
            Listing.description,
            Listing.params,
            Seller.name,
            Seller.url,
            Listing.seller_id,
        )
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .outerjoin(Seller, Seller.id == Listing.seller_id)
        .outerjoin(
            ListingExclusion,
            (ListingExclusion.listing_id == Listing.id) & (ListingExclusion.search_id == search_id),
        )
        .where(
            SearchListing.search_id == search_id,
            Listing.status == "active",
            Listing.is_flagged.is_(False),
            Listing.current_price.is_not(None),
        )
    )
    if isinstance(max_age_days, int) and not isinstance(max_age_days, bool) and max_age_days > 0:
        statement = statement.where(
            SearchListing.first_seen >= datetime.now(UTC) - timedelta(days=max_age_days)
        )
    rows = await session.execute(statement)
    filtered: list[FilteredListing] = []
    for (
        title,
        price,
        listing_region,
        manual_id,
        description,
        listing_params,
        seller_name,
        seller_url,
        seller_id,
    ) in rows.all():
        if price is None:
            continue
        text = combined_text(title or "", description)
        word = first_matching_exclude(text, excludes)
        reason: str | None = None
        if manual_id is not None:
            reason = "manual"
        elif groups and not matches_keyword_groups(text, groups):
            reason = "keyword"
        elif word is not None and (
            first_matching_exclude(title or "", excludes) is not None
            or not desc_verdict_ok(listing_params, word)
        ):
            reason = "stopword"
        elif (target_refs or exclude_refs) and seller_filter_reason(
            name=seller_name,
            url=seller_url,
            target_refs=target_refs,
            exclude_refs=exclude_refs,
            seller_id=seller_id,
        ) is not None:
            reason = "seller"
        elif not matches_region(listing_region, regions, exclude_regions):
            reason = "region"
        filtered.append(FilteredListing(title=title or "", price=float(price), reason=reason))
    return filtered


async def _active_listings(
    session: AsyncSession, search_id: uuid.UUID
) -> tuple[list[float], ExclusionCounts]:
    """Цены активных объявлений (без флагов) после всех фильтров поиска."""
    counters: dict[str, int] = {
        "keyword": 0,
        "stopword": 0,
        "region": 0,
        "manual": 0,
        "seller": 0,
    }
    prices: list[float] = []
    for row in await _filtered_listings(session, search_id):
        if row.reason is None:
            prices.append(row.price)
        else:
            counters[row.reason] = counters.get(row.reason, 0) + 1
    return prices, ExclusionCounts(**counters)


async def filtered_top_listings(
    session: AsyncSession, search_id: uuid.UUID, limit: int
) -> list[tuple[str, float | None]]:
    """Топ выдачи для AI-дайджеста — только объявления, прошедшие фильтры поиска."""
    rows = await _filtered_listings(session, search_id)
    top: list[tuple[str, float | None]] = [
        (row.title, row.price) for row in rows if row.reason is None
    ]
    return top[:limit]


async def _active_prices(session: AsyncSession, search_id: uuid.UUID) -> list[float]:
    prices, _ = await _active_listings(session, search_id)
    return prices


async def _flagged_count(session: AsyncSession, search_id: uuid.UUID) -> int:
    rows = await session.execute(
        select(func.count())
        .select_from(Listing)
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .where(
            SearchListing.search_id == search_id,
            Listing.status == "active",
            Listing.is_flagged.is_(True),
        )
    )
    return int(rows.scalar_one() or 0)


async def _flag_categories(session: AsyncSession, search_id: uuid.UUID) -> dict[str, int]:
    rows = await session.execute(
        select(Listing.flag_category, func.count())
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .where(
            SearchListing.search_id == search_id,
            Listing.status == "active",
            Listing.is_flagged.is_(True),
            Listing.flag_category.is_not(None),
        )
        .group_by(Listing.flag_category)
    )
    return {row[0]: int(row[1]) for row in rows.all() if row[0]}


async def _count_new(
    session: AsyncSession, search_id: uuid.UUID, start: datetime, end: datetime
) -> int:
    rows = await session.execute(
        select(func.count())
        .select_from(SearchListing)
        .where(
            SearchListing.search_id == search_id,
            SearchListing.first_seen >= start,
            SearchListing.first_seen < end,
        )
    )
    return int(rows.scalar_one())


async def _gone_lifetimes(
    session: AsyncSession, search_id: uuid.UUID, start: datetime, end: datetime
) -> list[float]:
    rows = await session.execute(
        select(Listing.first_seen, Listing.last_seen)
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .where(
            SearchListing.search_id == search_id,
            Listing.status == "gone",
            Listing.last_seen >= start,
            Listing.last_seen < end,
        )
    )
    return [
        (last_seen - first_seen).total_seconds() / 86400 for first_seen, last_seen in rows.all()
    ]


def _gone_query(search_id: uuid.UUID, start: datetime, end: datetime) -> Select[int]:
    return (
        select(func.count())
        .select_from(Listing)
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .where(
            SearchListing.search_id == search_id,
            Listing.status == "gone",
            Listing.last_seen >= start,
            Listing.last_seen < end,
        )
    )


async def _count_gone(
    session: AsyncSession, search_id: uuid.UUID, start: datetime, end: datetime
) -> int:
    rows = await session.execute(_gone_query(search_id, start, end))
    return int(rows.scalar_one())


async def recalc_daily_analytics(
    session: AsyncSession, search_id: uuid.UUID, day: date | None = None
) -> date:
    """Пересчитывает и сохраняет дневной агрегат по поиску."""
    target_day = day or datetime.now(UTC).date()
    day_start, day_end = _day_bounds(target_day)

    prices = await _active_prices(session, search_id)
    new_today = await _count_new(session, search_id, day_start, day_end)
    gone_today = await _count_gone(session, search_id, day_start, day_end)
    lifetimes = await _gone_lifetimes(session, search_id, day_start, day_end)
    avg_lifetime = sum(lifetimes) / len(lifetimes) if lifetimes else None
    stats = compute_price_stats(prices) if prices else None

    values = {
        "search_id": search_id,
        "calc_date": target_day,
        "active_count": len(prices),
        "new_today_count": new_today,
        "delisted_today_count": gone_today,
        "price_min": stats.price_min if stats else None,
        "price_max": stats.price_max if stats else None,
        "price_median": stats.median if stats else None,
        "price_p25": stats.p25 if stats else None,
        "price_p75": stats.p75 if stats else None,
        "avg_lifetime_days": avg_lifetime,
    }
    statement = pg_insert(MarketAnalyticsDaily).values(**values)
    statement = statement.on_conflict_do_update(
        index_elements=["search_id", "calc_date"],
        set_={key: value for key, value in values.items() if key not in ("search_id", "calc_date")},
    )
    await session.execute(statement)
    return target_day


async def build_search_summary(session: AsyncSession, search_id: uuid.UUID) -> MarketSummary:
    """Текущая сводка рынка по поиску: живые цены + активность за окна."""
    now = datetime.now(UTC)
    day_start, day_end = _day_bounds(now.date())
    week_start = day_start - timedelta(days=7)
    lifetime_start = day_start - timedelta(days=LIFETIME_WINDOW_DAYS)

    prices, excluded = await _active_listings(session, search_id)
    new_today = await _count_new(session, search_id, day_start, day_end)
    gone_today = await _count_gone(session, search_id, day_start, day_end)
    delisted_7d = await _count_gone(session, search_id, week_start, day_end)
    lifetimes = await _gone_lifetimes(session, search_id, lifetime_start, day_end)
    summary = build_market_summary(prices, new_today, gone_today, delisted_7d, lifetimes)
    return replace(
        summary,
        flagged_count=await _flagged_count(session, search_id),
        flag_categories=await _flag_categories(session, search_id),
        keyword_excluded=excluded.keyword,
        stopword_excluded=excluded.stopword,
        region_excluded=excluded.region,
        manual_excluded=excluded.manual,
        seller_excluded=excluded.seller,
    )


async def fetch_daily_history(
    session: AsyncSession, search_id: uuid.UUID, days: int = SUMMARY_HISTORY_DAYS
) -> list[MarketAnalyticsDaily]:
    cutoff = datetime.now(UTC).date() - timedelta(days=days)
    rows = await session.execute(
        select(MarketAnalyticsDaily)
        .where(
            MarketAnalyticsDaily.search_id == search_id,
            MarketAnalyticsDaily.calc_date >= cutoff,
        )
        .order_by(MarketAnalyticsDaily.calc_date)
    )
    return list(rows.scalars().all())
