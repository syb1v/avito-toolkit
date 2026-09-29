from dataclasses import dataclass
from enum import StrEnum

from app.services.analytics.aggregates import delisting_velocity

DEFAULT_DELISTING_THRESHOLD = 0.35
UNDERCUT_FACTOR = 0.99


class PricingStrategy(StrEnum):
    UNDERCUT_P25 = "undercut_p25"
    MATCH_MEDIAN = "match_median"
    PREMIUM_P75 = "premium_p75"
    KEEP_CURRENT = "keep_current"


@dataclass(frozen=True, slots=True)
class RepricingContext:
    median: float
    p25: float
    p75: float
    active_competitors: int
    delisted_7d: int
    active_total: int


@dataclass(frozen=True, slots=True)
class PriceTarget:
    strategy: PricingStrategy
    target_price: float
    clamped_price: float
    delta_pct: float
    requires_approval: bool


def suggest_strategy(
    context: RepricingContext, threshold: float = DEFAULT_DELISTING_THRESHOLD
) -> PricingStrategy:
    """Высокое вымывание выдачи — держим цену у P75, низкое — уходим к P25."""
    velocity = delisting_velocity(context.delisted_7d, context.active_total)
    if context.active_total <= 0:
        return PricingStrategy.KEEP_CURRENT
    if velocity > threshold:
        return PricingStrategy.PREMIUM_P75
    if velocity < threshold / 2:
        return PricingStrategy.UNDERCUT_P25
    return PricingStrategy.MATCH_MEDIAN


def strategy_target(
    context: RepricingContext, strategy: PricingStrategy, current_price: float
) -> float:
    match strategy:
        case PricingStrategy.UNDERCUT_P25:
            return max(0.0, context.p25 * UNDERCUT_FACTOR)
        case PricingStrategy.MATCH_MEDIAN:
            return context.median
        case PricingStrategy.PREMIUM_P75:
            return context.p75
        case PricingStrategy.KEEP_CURRENT:
            return current_price


def build_price_target(
    context: RepricingContext,
    current_price: float,
    min_price: float | None = None,
    max_price: float | None = None,
    strategy: PricingStrategy | None = None,
    max_step_pct: float = 5.0,
    hitl_threshold_pct: float = 10.0,
) -> PriceTarget:
    """Стратегия → ограничение шага → коридор [min_price, max_price] → HITL-флаг."""
    chosen = strategy or suggest_strategy(context)
    target = strategy_target(context, chosen, current_price)

    stepped = target
    if current_price > 0:
        max_step = current_price * max_step_pct / 100
        if abs(target - current_price) > max_step:
            direction = 1.0 if target > current_price else -1.0
            stepped = current_price + direction * max_step

    clamped = stepped
    if min_price is not None:
        clamped = max(clamped, min_price)
    if max_price is not None:
        clamped = min(clamped, max_price)

    delta_pct = 0.0 if current_price <= 0 else (clamped - current_price) / current_price * 100
    return PriceTarget(
        strategy=chosen,
        target_price=target,
        clamped_price=clamped,
        delta_pct=delta_pct,
        requires_approval=abs(delta_pct) > hitl_threshold_pct,
    )
