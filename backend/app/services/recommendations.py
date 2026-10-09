from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.matching import build_overview
from app.services.pricing import RepricingContext, build_price_target

DETERMINISTIC_DELISTED_7D = 0


@dataclass(frozen=True, slots=True)
class Recommendation:
    sku: str
    title: str
    our_price: float
    cost_price: float | None
    market_median: float | None
    matched_count: int
    strategy: str
    target_price: float
    clamped_price: float
    delta_pct: float
    requires_approval: bool
    market_p25: float | None = None
    market_p75: float | None = None


def build_recommendation(
    *,
    sku: str,
    title: str,
    our_price: float,
    cost_price: float | None,
    market_median: float | None,
    market_p25: float | None,
    market_p75: float | None,
    matched_count: int,
    max_step_pct: float = 5.0,
    hitl_threshold_pct: float = 10.0,
) -> Recommendation | None:
    """Детерминированная рекомендация цены по позиции SKU относительно рынка."""
    if market_median is None or market_p25 is None or market_p75 is None:
        return None
    if matched_count <= 0 or our_price <= 0:
        return None
    context = RepricingContext(
        median=market_median,
        p25=market_p25,
        p75=market_p75,
        active_competitors=matched_count,
        delisted_7d=DETERMINISTIC_DELISTED_7D,
        active_total=matched_count,
    )
    target = build_price_target(
        context,
        our_price,
        min_price=cost_price,
        max_step_pct=max_step_pct,
        hitl_threshold_pct=hitl_threshold_pct,
    )
    return Recommendation(
        sku=sku,
        title=title,
        our_price=our_price,
        cost_price=cost_price,
        market_median=market_median,
        market_p25=market_p25,
        market_p75=market_p75,
        matched_count=matched_count,
        strategy=target.strategy.value,
        target_price=target.target_price,
        clamped_price=target.clamped_price,
        delta_pct=target.delta_pct,
        requires_approval=target.requires_approval,
    )


async def build_recommendations(session: AsyncSession) -> list[Recommendation]:
    """Рекомендации по всем нашим SKU с матчами на рынке."""
    settings = get_settings()
    recommendations: list[Recommendation] = []
    for row in await build_overview(session):
        recommendation = build_recommendation(
            sku=row.sku,
            title=row.title,
            our_price=row.our_price,
            cost_price=row.cost_price,
            market_median=row.market_median,
            market_p25=row.market_p25,
            market_p75=row.market_p75,
            matched_count=row.matched_count,
            max_step_pct=settings.reprice_max_step_pct,
            hitl_threshold_pct=settings.reprice_hitl_threshold_pct,
        )
        if recommendation is not None:
            recommendations.append(recommendation)
    return recommendations
