import pytest

from app.services.pricing import (
    PricingStrategy,
    RepricingContext,
    build_price_target,
    suggest_strategy,
)

BASE_CONTEXT = RepricingContext(
    median=2000.0,
    p25=1800.0,
    p75=2200.0,
    active_competitors=80,
    delisted_7d=25,
    active_total=100,
)


def test_suggest_strategy_high_delisting_velocity() -> None:
    context = RepricingContext(2000.0, 1800.0, 2200.0, 80, 50, 100)
    assert suggest_strategy(context) is PricingStrategy.PREMIUM_P75


def test_suggest_strategy_low_delisting_velocity() -> None:
    context = RepricingContext(2000.0, 1800.0, 2200.0, 80, 10, 100)
    assert suggest_strategy(context) is PricingStrategy.UNDERCUT_P25


def test_suggest_strategy_balanced_market() -> None:
    assert suggest_strategy(BASE_CONTEXT) is PricingStrategy.MATCH_MEDIAN


def test_step_limit_caps_price_change() -> None:
    target = build_price_target(
        BASE_CONTEXT,
        current_price=1000.0,
        strategy=PricingStrategy.MATCH_MEDIAN,
        max_step_pct=5.0,
    )
    assert target.target_price == pytest.approx(2000.0)
    assert target.clamped_price == pytest.approx(1050.0)
    assert target.delta_pct == pytest.approx(5.0)
    assert target.requires_approval is False


def test_min_price_clamp_triggers_approval() -> None:
    target = build_price_target(
        BASE_CONTEXT,
        current_price=1000.0,
        min_price=1200.0,
        strategy=PricingStrategy.MATCH_MEDIAN,
    )
    assert target.clamped_price == pytest.approx(1200.0)
    assert target.delta_pct == pytest.approx(20.0)
    assert target.requires_approval is True


def test_max_price_clamp() -> None:
    target = build_price_target(
        BASE_CONTEXT,
        current_price=2100.0,
        max_price=2000.0,
        strategy=PricingStrategy.PREMIUM_P75,
    )
    assert target.clamped_price == pytest.approx(2000.0)


def test_undercut_uses_p25_minus_one_percent() -> None:
    target = build_price_target(
        BASE_CONTEXT,
        current_price=1800.0,
        strategy=PricingStrategy.UNDERCUT_P25,
    )
    assert target.target_price == pytest.approx(1800.0 * 0.99)


def test_keep_current_strategy_keeps_price() -> None:
    target = build_price_target(
        BASE_CONTEXT,
        current_price=1500.0,
        strategy=PricingStrategy.KEEP_CURRENT,
    )
    assert target.clamped_price == pytest.approx(1500.0)
    assert target.delta_pct == 0.0
