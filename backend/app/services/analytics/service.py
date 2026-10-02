import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Listing, MarketAnalyticsDaily, SearchListing
from app.services.analytics.aggregates import MarketSummary, build_market_summary
from app.services.analytics.iqr import compute_price_stats

LIFETIME_WINDOW_DAYS = 30
SUMMARY_HISTORY_DAYS = 30


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


async def _active_prices(session: AsyncSession, search_id: uuid.UUID) -> list[float]:
    rows = await session.execute(
        select(Listing.current_price)
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .where(
            SearchListing.search_id == search_id,
            Listing.status == "active",
            Listing.is_flagged.is_(False),
            Listing.current_price.is_not(None),
        )
    )
    return [float(row[0]) for row in rows.all() if row[0] is not None]


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

    prices = await _active_prices(session, search_id)
    new_today = await _count_new(session, search_id, day_start, day_end)
    gone_today = await _count_gone(session, search_id, day_start, day_end)
    delisted_7d = await _count_gone(session, search_id, week_start, day_end)
    lifetimes = await _gone_lifetimes(session, search_id, lifetime_start, day_end)
    summary = build_market_summary(prices, new_today, gone_today, delisted_7d, lifetimes)
    return replace(
        summary,
        flagged_count=await _flagged_count(session, search_id),
        flag_categories=await _flag_categories(session, search_id),
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
