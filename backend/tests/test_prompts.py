from app.ai.prompts import build_digest_prompt, build_price_prompt
from app.services.pricing import RepricingContext


def test_build_digest_prompt_contains_metrics() -> None:
    prompt = build_digest_prompt(
        search_name="iPhone 15",
        active_count=42,
        new_today=3,
        delisted_today=1,
        delisted_7d=12,
        delisting_velocity=0.2857,
        median=62500,
        p25=54000,
        p75=68000,
        top_listings=[("iPhone 15 128 GB", 75000)],
        history=[("2026-09-29", 62500)],
    )
    assert "iPhone 15" in prompt
    assert "62500" in prompt
    assert "0.286" in prompt
    assert "iPhone 15 128 GB" in prompt
    assert "2026-09-29" in prompt


def test_build_digest_prompt_handles_empty_data() -> None:
    prompt = build_digest_prompt(
        search_name="Пустой поиск",
        active_count=0,
        new_today=0,
        delisted_today=0,
        delisted_7d=0,
        delisting_velocity=0.0,
        median=None,
        p25=None,
        p75=None,
        top_listings=[],
    )
    assert "нет данных" in prompt


def test_build_price_prompt_includes_cost_line() -> None:
    context = RepricingContext(
        median=100.0,
        p25=90.0,
        p75=110.0,
        active_competitors=10,
        delisted_7d=2,
        active_total=10,
    )
    with_cost = build_price_prompt(
        title="Товар", current_price=95.0, cost_price=70.0, context=context
    )
    assert "Себестоимость: 70.0 руб." in with_cost
    without_cost = build_price_prompt(
        title="Товар", current_price=95.0, cost_price=None, context=context
    )
    assert "не задана" in without_cost
