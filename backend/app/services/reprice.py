"""Авто-правки цен: состояние тумблера, отбор SKU, последний прогон."""

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from redis.asyncio import Redis

from app.config import Settings
from app.services.recommendations import Recommendation

logger = logging.getLogger(__name__)

STATE_KEY = "reprice:auto"
LAST_KEY = "reprice:auto:last"
LAST_TTL_SECONDS = 7 * 24 * 3600
MIN_DELTA_PCT = 0.05


@dataclass(frozen=True, slots=True)
class AutoRepriceState:
    enabled: bool
    live: bool

    @property
    def mode(self) -> str:
        return "live" if self.live else "dry_run"


async def get_auto_reprice_state(redis: Redis, settings: Settings) -> AutoRepriceState:
    """Состояние тумблера: Redis, при отсутствии — env-дефолт (выкл)."""
    raw = await redis.get(STATE_KEY)
    if raw:
        try:
            data = json.loads(raw)
            return AutoRepriceState(enabled=bool(data.get("enabled")), live=bool(data.get("live")))
        except (TypeError, ValueError):
            logger.warning("broken reprice state in redis, using env default")
    return AutoRepriceState(enabled=settings.reprice_auto_enabled, live=False)


async def set_auto_reprice_state(redis: Redis, *, enabled: bool, live: bool) -> AutoRepriceState:
    state = AutoRepriceState(enabled=enabled, live=live and enabled)
    await redis.set(STATE_KEY, json.dumps({"enabled": state.enabled, "live": state.live}))
    return state


async def save_last_run(redis: Redis, payload: dict[str, Any]) -> None:
    await redis.set(
        LAST_KEY,
        json.dumps(payload, ensure_ascii=False, default=str),
        ex=LAST_TTL_SECONDS,
    )


async def load_last_run(redis: Redis) -> dict[str, Any] | None:
    raw = await redis.get(LAST_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def next_run_at(settings: Settings, now: datetime | None = None) -> str | None:
    """Ближайший запуск ночного задания по cron из настроек."""
    try:
        trigger = CronTrigger.from_crontab(settings.reprice_auto_cron, timezone="UTC")
        moment = now or datetime.now(UTC)
        fire = trigger.get_next_fire_time(None, moment)
        return fire.isoformat() if fire is not None else None
    except ValueError:
        return None


def select_recommendations(
    recommendations: Sequence[Recommendation],
    *,
    busy_skus: set[str],
    active_skus: dict[str, tuple[int | None, str | None]],
    min_delta_pct: float = MIN_DELTA_PCT,
) -> list[Recommendation]:
    """SKU к авто-правке: активные, привязанные к Авито, без открытой правки и с Δ>0."""
    selected: list[Recommendation] = []
    for recommendation in recommendations:
        if recommendation.sku in busy_skus:
            continue
        meta = active_skus.get(recommendation.sku)
        if meta is None:
            continue
        avito_item_id, avito_url = meta
        if avito_item_id is None or not avito_url:
            continue
        if abs(recommendation.delta_pct) < min_delta_pct:
            continue
        if recommendation.clamped_price <= 0:
            continue
        selected.append(recommendation)
    return selected
