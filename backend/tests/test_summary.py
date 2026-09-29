import pytest

from app.services.analytics.aggregates import (
    build_market_summary,
    compute_daily_analytics,
)


def test_build_market_summary_filters_outlier() -> None:
    summary = build_market_summary(
        [100, 110, 120, 130, 140, 1000],
        new_today_count=2,
        delisted_today_count=1,
        delisted_7d=10,
    )
    assert summary.active_count == 6
    assert summary.stats is not None
    assert summary.stats.count == 5
    assert summary.stats.median == pytest.approx(120.0)
    assert summary.stats.price_max == pytest.approx(140.0)
    assert summary.delisting_velocity == pytest.approx(10 / 6)
    assert summary.avg_lifetime_days is None


def test_build_market_summary_empty_market() -> None:
    summary = build_market_summary([], 0, 0, 0)
    assert summary.active_count == 0
    assert summary.stats is None
    assert summary.delisting_velocity == 0.0


def test_build_market_summary_averages_lifetimes() -> None:
    summary = build_market_summary([100], 0, 0, 0, lifetimes_days=[2.0, 4.0])
    assert summary.avg_lifetime_days == pytest.approx(3.0)


def test_compute_daily_analytics_without_prices() -> None:
    daily = compute_daily_analytics([], new_today_count=5, delisted_today_count=3)
    assert daily.stats is None
    assert daily.active_count == 0
    assert daily.new_today_count == 5
    assert daily.delisted_today_count == 3
