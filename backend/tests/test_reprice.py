import json
from datetime import UTC, datetime

import pytest

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


def test_pick_http_sibling_for_socks5() -> None:
    from app.services.proxy_pool import parse_proxy_entry, pick_http_sibling

    entries = [
        parse_proxy_entry("http://user:pass@gate.psnode.me:3130"),
        parse_proxy_entry("socks5://user:pass@gate2.psnode.me:1081"),
    ]
    assert (
        pick_http_sibling("socks5://user:pass@gate.psnode.me:1081", entries)
        == "http://user:pass@gate.psnode.me:3130"
    )
    assert pick_http_sibling("socks5://user:other@gate.psnode.me:1081", entries) is None
    assert pick_http_sibling("http://user:pass@gate.psnode.me:3130", entries) is None


def test_search_params_exclude_regions() -> None:
    from app.services.import_file import search_params

    params = search_params(
        query="beoplay eleven",
        keyword_groups=[["beoplay eleven"]],
        exclude_keywords=["black"],
        regions=["krasnodar"],
        exclude_regions=["moskva", "spb"],
    )
    assert params["regions"] == ["krasnodar"]
    assert params["exclude_regions"] == ["moskva", "spb"]


def test_avito_api_helpers() -> None:
    from app.config import Settings
    from app.services.avito_api import api_configured, parse_error

    assert not api_configured(Settings())
    assert api_configured(Settings(avito_client_id="x", avito_client_secret="y"))

    error = parse_error(403, '{"error":{"code":403,"message":"You are not item owner"}}')
    assert error.code == 403
    assert "not item owner" in error.message
    plain = parse_error(500, "boom")
    assert plain.code == 500
    assert plain.message == "boom"


def test_extract_item_price_variants() -> None:
    from app.workers.tasks import _extract_price

    assert _extract_price({"price": 2437}) == 2437.0
    assert _extract_price({"price": {"value": 42000}}) == 42000.0
    assert _extract_price({"price": {"amount": "1500"}}) is None
    assert _extract_price({}) is None


async def test_events_pubsub_roundtrip() -> None:
    import asyncio

    fakeredis = pytest.importorskip("fakeredis.aioredis")
    from app.services.events import CHANNEL, publish

    redis = fakeredis.FakeRedis()
    try:
        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL)

        async def read_one() -> dict:
            async for item in pubsub.listen():
                if item.get("type") == "message":
                    return item
            raise AssertionError("no message")

        task = asyncio.create_task(read_one())
        await publish(redis, "test.event", value=42)
        message = await asyncio.wait_for(task, timeout=2)
        assert message is not None
        payload = json.loads(message["data"])
        assert payload["type"] == "test.event"
        assert payload["payload"]["value"] == 42
        assert "ts" in payload
        await pubsub.aclose()
    finally:
        await redis.aclose()
