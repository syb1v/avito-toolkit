from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Listing, OurListing, ProductMarketMatch
from app.services.analytics.iqr import PriceStats, compute_price_stats

MATCH_STATUSES = ("auto_matched", "confirmed", "rejected")


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    listing_id: int
    title: str
    price: float | None


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate: MatchCandidate
    score: float


@dataclass(frozen=True, slots=True)
class MatchView:
    listing_id: int
    title: str
    price: float | None
    url: str | None
    status: str
    similarity_score: float


@dataclass(frozen=True, slots=True)
class MarketPosition:
    our_price: float
    matched_count: int
    stats: PriceStats | None
    cheaper_share: float | None
    delta_to_median_pct: float | None


@dataclass(frozen=True, slots=True)
class OverviewRow:
    sku: str
    title: str
    our_price: float
    is_active: bool
    avito_status: str | None
    avito_url: str | None
    matched_count: int
    market_median: float | None
    delta_to_median_pct: float | None
    cheaper_share: float | None


def rank_candidates(
    query: str,
    candidates: Sequence[MatchCandidate],
    min_score: float = 75.0,
    limit: int = 10,
) -> list[RankedCandidate]:
    """Нечёткий матчинг заголовков через rapidfuzz (token_set_ratio)."""
    choices = {candidate.listing_id: candidate.title for candidate in candidates}
    if not choices:
        return []
    results = process.extract(
        query,
        choices,
        scorer=fuzz.token_set_ratio,
        limit=limit,
        score_cutoff=min_score,
    )
    by_id = {candidate.listing_id: candidate for candidate in candidates}
    return [RankedCandidate(by_id[listing_id], float(score)) for _, score, listing_id in results]


def compute_market_position(
    our_price: float, prices: Sequence[float], use_iqr: bool = True
) -> MarketPosition:
    if not prices:
        return MarketPosition(our_price, 0, None, None, None)
    stats = compute_price_stats(prices, use_iqr=use_iqr)
    cheaper = sum(1 for price in prices if price < our_price)
    return MarketPosition(
        our_price=our_price,
        matched_count=len(prices),
        stats=stats,
        cheaper_share=cheaper / len(prices),
        delta_to_median_pct=(our_price - stats.median) / stats.median * 100,
    )


async def match_our_listing(session: AsyncSession, sku: str) -> list[RankedCandidate]:
    """Подбирает конкурентов для нашего SKU и сохраняет матчи."""
    our = await session.get(OurListing, sku)
    if our is None:
        raise LookupError(f"our listing {sku} not found")
    settings = get_settings()
    rows = await session.execute(
        select(Listing.id, Listing.title, Listing.current_price)
        .where(Listing.status == "active", Listing.current_price.is_not(None))
        .order_by(Listing.last_seen.desc())
        .limit(settings.match_max_candidates)
    )
    candidates = [
        MatchCandidate(row[0], row[1], float(row[2]) if row[2] is not None else None)
        for row in rows.all()
    ]
    ranked = rank_candidates(
        our.title,
        candidates,
        min_score=float(settings.match_min_score),
        limit=settings.match_top_n,
    )
    if ranked:
        now = datetime.now(UTC)
        statement = pg_insert(ProductMarketMatch).values(
            [
                {
                    "our_sku_id": sku,
                    "market_listing_id": ranked_item.candidate.listing_id,
                    "similarity_score": ranked_item.score,
                    "match_status": "auto_matched",
                    "matched_at": now,
                }
                for ranked_item in ranked
            ]
        )
        statement = statement.on_conflict_do_update(
            index_elements=[
                ProductMarketMatch.our_sku_id,
                ProductMarketMatch.market_listing_id,
            ],
            set_={
                "similarity_score": statement.excluded.similarity_score,
                "matched_at": statement.excluded.matched_at,
            },
            where=ProductMarketMatch.match_status == "auto_matched",
        )
        await session.execute(statement)
        await session.commit()
    return ranked


async def list_matches(session: AsyncSession, sku: str) -> list[MatchView]:
    rows = await session.execute(
        select(ProductMarketMatch, Listing)
        .join(Listing, Listing.id == ProductMarketMatch.market_listing_id)
        .where(ProductMarketMatch.our_sku_id == sku)
        .order_by(ProductMarketMatch.similarity_score.desc())
    )
    views: list[MatchView] = []
    for match, listing in rows.all():
        views.append(
            MatchView(
                listing_id=listing.id,
                title=listing.title,
                price=float(listing.current_price) if listing.current_price is not None else None,
                url=listing.url,
                status=match.match_status,
                similarity_score=match.similarity_score,
            )
        )
    return views


async def update_match_status(
    session: AsyncSession, sku: str, listing_id: int, status: str
) -> bool:
    if status not in MATCH_STATUSES:
        raise ValueError(f"unknown match status: {status}")
    match = await session.get(ProductMarketMatch, (sku, listing_id))
    if match is None:
        return False
    match.match_status = status
    await session.commit()
    return True


async def build_our_position(session: AsyncSession, sku: str) -> MarketPosition | None:
    our = await session.get(OurListing, sku)
    if our is None:
        raise LookupError(f"our listing {sku} not found")
    rows = await session.execute(
        select(Listing.current_price)
        .join(ProductMarketMatch, ProductMarketMatch.market_listing_id == Listing.id)
        .where(
            ProductMarketMatch.our_sku_id == sku,
            ProductMarketMatch.match_status != "rejected",
            Listing.current_price.is_not(None),
        )
    )
    prices = [float(row[0]) for row in rows.all() if row[0] is not None]
    if not prices:
        return None
    return compute_market_position(float(our.price), prices)


async def match_all_our_listings(session: AsyncSession) -> int:
    """Прогоняет матчинг по всем активным нашим SKU."""
    rows = await session.execute(
        select(OurListing.sku).where(OurListing.is_active.is_(True)).order_by(OurListing.sku)
    )
    matched = 0
    for (sku,) in rows.all():
        await match_our_listing(session, sku)
        matched += 1
    return matched


async def build_overview(session: AsyncSession) -> list[OverviewRow]:
    """Сводка по нашим SKU: цена, статус на Авито, матчи и дельта к медиане."""
    our_rows = (await session.execute(select(OurListing).order_by(OurListing.sku))).scalars().all()
    price_rows = await session.execute(
        select(ProductMarketMatch.our_sku_id, Listing.current_price)
        .join(Listing, Listing.id == ProductMarketMatch.market_listing_id)
        .where(
            ProductMarketMatch.match_status != "rejected",
            Listing.current_price.is_not(None),
        )
    )
    grouped: dict[str, list[float]] = {}
    for sku, price in price_rows.all():
        if price is not None:
            grouped.setdefault(sku, []).append(float(price))

    overview: list[OverviewRow] = []
    for our in our_rows:
        prices = grouped.get(our.sku, [])
        position = compute_market_position(float(our.price), prices) if prices else None
        overview.append(
            OverviewRow(
                sku=our.sku,
                title=our.title,
                our_price=float(our.price),
                is_active=our.is_active,
                avito_status=our.avito_status,
                avito_url=our.avito_url,
                matched_count=position.matched_count if position is not None else 0,
                market_median=(
                    position.stats.median
                    if position is not None and position.stats is not None
                    else None
                ),
                delta_to_median_pct=(
                    position.delta_to_median_pct if position is not None else None
                ),
                cheaper_share=position.cheaper_share if position is not None else None,
            )
        )
    return overview
