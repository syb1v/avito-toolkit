from datetime import UTC, datetime

from app.config import Settings
from app.services.recommendations import Recommendation
from app.services.reprice import (
    AutoRepriceState,
    get_auto_reprice_state,
    next_run_at,
    select_recommendations,
    set_auto_reprice_state,
)


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value


def _rec(sku: str, *, delta_pct: float = 1.0, clamped: float = 101.0) -> Recommendation:
    return Recommendation(
        sku=sku,
        title="Товар",
        our_price=100.0,
        cost_price=None,
        market_median=110.0,
        matched_count=5,
        strategy="match_median",
        target_price=clamped,
        clamped_price=clamped,
        delta_pct=delta_pct,
        requires_approval=False,
        market_p25=105.0,
        market_p75=115.0,
    )


def test_select_recommendations_filters() -> None:
    recommendations = [_rec("ok"), _rec("busy"), _rec("tiny", delta_pct=0.01), _rec("nolink")]
    selected = select_recommendations(
        recommendations,
        busy_skus={"busy"},
        active_skus={
            "ok": (111, "https://www.avito.ru/item_111"),
            "busy": (222, "https://www.avito.ru/item_222"),
            "tiny": (333, "https://www.avito.ru/item_333"),
            "nolink": (None, None),
        },
    )
    assert [item.sku for item in selected] == ["ok"]


def test_select_recommendations_skips_missing_sku_meta() -> None:
    assert select_recommendations([_rec("ghost")], busy_skus=set(), active_skus={}) == []


async def test_toggle_state_roundtrip_and_defaults() -> None:
    redis = FakeRedis()
    settings = Settings(reprice_auto_enabled=False, seller_edit_mode="dry_run")
    state = await get_auto_reprice_state(redis, settings)  # type: ignore[arg-type]
    assert state == AutoRepriceState(enabled=False, live=False)
    assert state.mode == "dry_run"

    updated = await set_auto_reprice_state(redis, enabled=True, live=True)  # type: ignore[arg-type]
    assert updated.enabled is True
    assert updated.live is True
    assert updated.mode == "live"
    assert (await get_auto_reprice_state(redis, settings)).live is True  # type: ignore[arg-type]

    disabled = await set_auto_reprice_state(redis, enabled=False, live=True)  # type: ignore[arg-type]
    assert disabled.live is False


def test_next_run_at() -> None:
    settings = Settings(reprice_auto_cron="0 0 * * *")
    now = datetime(2026, 10, 9, 15, 30, tzinfo=UTC)
    assert next_run_at(settings, now) == "2026-10-10T00:00:00+00:00"
    assert next_run_at(Settings(reprice_auto_cron="not a cron"), now) is None


def test_auto_reprice_prompt_contains_metrics() -> None:
    from app.ai.prompts import build_reprice_summary_prompt

    prompt = build_reprice_summary_prompt(
        items=[("avito-1", "Товар", 100.0, 105.0, "match_median", 110.0, 105.0, 120.0, 7)]
    )
    assert "avito-1" in prompt
    assert "100 → стало 105" in prompt
    assert "медиана 110" in prompt
