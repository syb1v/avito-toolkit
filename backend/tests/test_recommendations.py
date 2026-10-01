from app.services.recommendations import build_recommendation

BASE_KWARGS = {
    "sku": "SKU-1",
    "title": "iPhone 15 128GB",
    "our_price": 50000.0,
    "cost_price": 40000.0,
    "market_median": 35000.0,
    "market_p25": 32000.0,
    "market_p75": 41000.0,
    "matched_count": 10,
}


def test_recommendation_returns_none_without_matches() -> None:
    recommendation = build_recommendation(**{**BASE_KWARGS, "matched_count": 0})
    assert recommendation is None


def test_recommendation_returns_none_without_price_stats() -> None:
    recommendation = build_recommendation(**{**BASE_KWARGS, "market_median": None})
    assert recommendation is None


def test_recommendation_deterministic_undercut() -> None:
    recommendation = build_recommendation(**BASE_KWARGS)
    assert recommendation is not None
    # velocity = 0 -> undercut_p25: 32000 * 0.99 = 31680; шаг ограничен 5%
    assert recommendation.strategy == "undercut_p25"
    assert recommendation.target_price == 31680.0
    assert recommendation.clamped_price == 47500.0
    assert recommendation.delta_pct == -5.0
    assert recommendation.requires_approval is False


def test_recommendation_min_price_keeps_margin() -> None:
    recommendation = build_recommendation(**{**BASE_KWARGS, "cost_price": 48000.0})
    assert recommendation is not None
    assert recommendation.clamped_price == 48000.0
    assert recommendation.delta_pct == -4.0
    assert recommendation.requires_approval is False


def test_recommendation_marks_approval_for_big_change() -> None:
    recommendation = build_recommendation(
        **{**BASE_KWARGS, "our_price": 100000.0, "max_step_pct": 50.0}
    )
    assert recommendation is not None
    assert recommendation.requires_approval is True
    assert recommendation.delta_pct == -50.0
    assert recommendation.clamped_price == 50000.0
