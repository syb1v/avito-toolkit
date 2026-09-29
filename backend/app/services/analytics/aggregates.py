from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.services.analytics.iqr import PriceStats, compute_price_stats


@dataclass(frozen=True, slots=True)
class DailyAnalytics:
    active_count: int
    new_today_count: int
    delisted_today_count: int
    stats: PriceStats | None
    avg_lifetime_days: float | None


def compute_daily_analytics(
    active_prices: Sequence[float],
    new_today_count: int,
    delisted_today_count: int,
    lifetimes_days: Iterable[float] | None = None,
    use_iqr: bool = True,
) -> DailyAnalytics:
    """Дневные агрегаты рынка по одному поиску."""
    stats: PriceStats | None = None
    if active_prices:
        stats = compute_price_stats(active_prices, use_iqr=use_iqr)
    lifetime_values = [float(value) for value in (lifetimes_days or [])]
    avg_lifetime = sum(lifetime_values) / len(lifetime_values) if lifetime_values else None
    return DailyAnalytics(
        active_count=len(active_prices),
        new_today_count=new_today_count,
        delisted_today_count=delisted_today_count,
        stats=stats,
        avg_lifetime_days=avg_lifetime,
    )


def delisting_velocity(delisted_7d: int, active_total: int) -> float:
    """Прокси-метрика спроса: доля вымывания выдачи за 7 дней."""
    if active_total <= 0:
        return 0.0
    return delisted_7d / active_total
