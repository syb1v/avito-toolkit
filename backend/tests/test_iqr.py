import pytest

from app.services.analytics.iqr import (
    compute_price_stats,
    filter_outliers,
    percentile,
)

SKEWED_PRICES = [100, 110, 120, 130, 140, 1000]


def test_percentile_linear_interpolation() -> None:
    assert percentile(SKEWED_PRICES, 25) == pytest.approx(112.5)
    assert percentile(SKEWED_PRICES, 50) == pytest.approx(125.0)
    assert percentile(SKEWED_PRICES, 75) == pytest.approx(137.5)


def test_percentile_validation() -> None:
    with pytest.raises(ValueError):
        percentile(SKEWED_PRICES, 101)
    with pytest.raises(ValueError):
        percentile([], 50)


def test_filter_outliers_drops_extreme_price() -> None:
    result = filter_outliers(SKEWED_PRICES)
    assert 1000.0 not in result.kept
    assert result.dropped == (1000.0,)
    assert result.lower_bound == pytest.approx(75.0)
    assert result.upper_bound == pytest.approx(175.0)


def test_filter_outliers_keeps_uniform_prices() -> None:
    result = filter_outliers([500, 500, 500])
    assert result.kept == (500.0, 500.0, 500.0)
    assert result.dropped == ()


def test_compute_price_stats_ignores_outlier() -> None:
    stats = compute_price_stats(SKEWED_PRICES)
    assert stats.count == 5
    assert stats.price_min == pytest.approx(100.0)
    assert stats.price_max == pytest.approx(140.0)
    assert stats.mean == pytest.approx(120.0)
    assert stats.median == pytest.approx(120.0)
    assert stats.p25 == pytest.approx(110.0)
    assert stats.p75 == pytest.approx(130.0)


def test_compute_price_stats_empty_raises() -> None:
    with pytest.raises(ValueError):
        compute_price_stats([])
