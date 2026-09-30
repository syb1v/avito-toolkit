from scripts.verify_analytics import all_match, cross_check


def test_cross_check_matches_polars_on_skewed_data() -> None:
    comparisons = cross_check([100, 110, 120, 130, 140, 1000])
    assert all_match(comparisons)
    values = {comparison.metric: comparison.ours for comparison in comparisons}
    assert values["count"] == 5
    assert values["price_min"] == 100.0
    assert values["price_max"] == 140.0
    assert values["mean"] == 120.0
    assert values["median"] == 120.0
    assert values["p25"] == 110.0
    assert values["p75"] == 130.0


def test_cross_check_equal_prices() -> None:
    comparisons = cross_check([500, 500, 500, 500])
    assert all_match(comparisons)
    values = {comparison.metric: comparison.ours for comparison in comparisons}
    assert values["median"] == 500.0
    assert values["p25"] == 500.0
    assert values["p75"] == 500.0
