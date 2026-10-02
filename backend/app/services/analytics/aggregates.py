from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from app.services.analytics.iqr import PriceStats, compute_price_stats


@dataclass(frozen=True, slots=True)
class DailyAnalytics:
    active_count: int
    new_today_count: int
    delisted_today_count: int
    stats: PriceStats | None
    avg_lifetime_days: float | None


@dataclass(frozen=True, slots=True)
class MarketSummary:
    active_count: int
    new_today_count: int
    delisted_today_count: int
    delisted_7d: int
    delisting_velocity: float
    avg_lifetime_days: float | None
    stats: PriceStats | None
    flagged_count: int = 0
    flag_categories: dict[str, int] = field(default_factory=dict)


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


def build_market_summary(
    active_prices: Sequence[float],
    new_today_count: int,
    delisted_today_count: int,
    delisted_7d: int,
    lifetimes_days: Iterable[float] | None = None,
    use_iqr: bool = True,
) -> MarketSummary:
    """Сводка рынка: цены с IQR-фильтрацией, активность и прокси-спрос."""
    daily = compute_daily_analytics(
        active_prices,
        new_today_count,
        delisted_today_count,
        lifetimes_days,
        use_iqr=use_iqr,
    )
    return MarketSummary(
        active_count=daily.active_count,
        new_today_count=daily.new_today_count,
        delisted_today_count=daily.delisted_today_count,
        delisted_7d=delisted_7d,
        delisting_velocity=delisting_velocity(delisted_7d, daily.active_count),
        avg_lifetime_days=daily.avg_lifetime_days,
        stats=daily.stats,
    )


def delisting_velocity(delisted_7d: int, active_total: int) -> float:
    """Прокси-метрика спроса: доля вымывания выдачи за 7 дней."""
    if active_total <= 0:
        return 0.0
    return delisted_7d / active_total
