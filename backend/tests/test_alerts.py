from app.services.alerts import evaluate_price_above_market


def test_alert_when_price_well_above_median() -> None:
    decision = evaluate_price_above_market(
        90000.0,
        [50000, 55000, 60000, 60000, 65000],
        threshold_pct=10.0,
        context={"search_id": "s1", "sku": "SKU-1"},
    )
    assert decision is not None
    assert decision.type == "price_above_market"
    assert decision.payload["sku"] == "SKU-1"
    assert decision.payload["market_median"] == 60000.0
    assert decision.payload["delta_pct"] == 50.0


def test_no_alert_within_threshold() -> None:
    decision = evaluate_price_above_market(
        63000.0,
        [50000, 55000, 60000, 60000, 65000],
        threshold_pct=10.0,
        context={},
    )
    assert decision is None


def test_no_alert_without_prices() -> None:
    decision = evaluate_price_above_market(10000.0, [], threshold_pct=10.0, context={})
    assert decision is None


def test_outlier_competitor_does_not_trigger_alert() -> None:
    # без IQR-фильтра медиана 62000 и дельта 10.48% > 10%, после фильтра медиана
    # 63000 и дельта 8.73% — алерта нет
    decision = evaluate_price_above_market(
        68500.0,
        [2000, 60000, 62000, 64000, 66000],
        threshold_pct=10.0,
        context={},
    )
    assert decision is None
