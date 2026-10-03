import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, String, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import (
    Alert,
    Listing,
    OurListing,
    ProductMarketMatch,
    Search,
    SearchListing,
)
from app.services.matching import compute_market_position

PRICE_ABOVE_MARKET = "price_above_market"


def search_alive_clause() -> ColumnElement[bool]:
    """Условие «алерт ссылается на существующий поиск» (сироты не показываем)."""
    return (
        select(Search.id)
        .where(cast(Search.id, String) == Alert.payload["search_id"].astext)
        .exists()
    )


@dataclass(frozen=True, slots=True)
class AlertDecision:
    type: str
    payload: dict[str, object]


def evaluate_price_above_market(
    our_price: float,
    prices: Sequence[float],
    threshold_pct: float,
    context: dict[str, object],
) -> AlertDecision | None:
    """Наша цена выше медианы рынка на threshold_pct процентов и более."""
    if not prices:
        return None
    position = compute_market_position(our_price, prices)
    if position.stats is None or position.stats.median <= 0:
        return None
    delta_pct = (our_price - position.stats.median) / position.stats.median * 100
    if delta_pct <= threshold_pct:
        return None
    payload: dict[str, object] = {
        **context,
        "our_price": our_price,
        "market_median": position.stats.median,
        "market_p25": position.stats.p25,
        "matched_count": len(prices),
        "delta_pct": round(delta_pct, 2),
    }
    return AlertDecision(type=PRICE_ABOVE_MARKET, payload=payload)


async def _has_open_alert(
    session: AsyncSession, search_id: uuid.UUID, sku: str, alert_type: str
) -> bool:
    rows = await session.execute(
        select(Alert.id)
        .where(
            Alert.type == alert_type,
            Alert.status == "new",
            Alert.payload["search_id"].astext == str(search_id),
            Alert.payload["sku"].astext == sku,
        )
        .limit(1)
    )
    return rows.first() is not None


async def evaluate_search_alerts(session: AsyncSession, search_id: uuid.UUID) -> list[Alert]:
    """Прогон правил по активным SKU; учитываются только лоты этого поиска.

    Иначе алерт по SKU создавался бы при обходе любого другого поиска и ссылался
    на поиск, к которому рынок не относится (и «жил» после удаления нужного поиска).
    """
    settings = get_settings()
    price_rows = await session.execute(
        select(ProductMarketMatch.our_sku_id, Listing.current_price)
        .join(Listing, Listing.id == ProductMarketMatch.market_listing_id)
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .where(
            SearchListing.search_id == search_id,
            ProductMarketMatch.match_status != "rejected",
            Listing.current_price.is_not(None),
        )
    )
    grouped: dict[str, list[float]] = {}
    for sku, price in price_rows.all():
        if price is not None:
            grouped.setdefault(sku, []).append(float(price))
    if not grouped:
        return []
    our_rows = await session.execute(
        select(OurListing).where(
            OurListing.is_active.is_(True),
            OurListing.sku.in_(list(grouped)),
        )
    )
    created: list[Alert] = []
    for our in our_rows.scalars().all():
        prices = grouped.get(our.sku, [])
        decision = evaluate_price_above_market(
            float(our.price),
            prices,
            settings.alert_price_above_market_pct,
            {"search_id": str(search_id), "sku": our.sku, "title": our.title},
        )
        if decision is None:
            continue
        if await _has_open_alert(session, search_id, our.sku, decision.type):
            continue
        alert = Alert(type=decision.type, payload=decision.payload, status="new")
        session.add(alert)
        created.append(alert)
    await session.flush()
    return created
