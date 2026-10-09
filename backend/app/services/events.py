"""Шина событий: Redis pub/sub для live-обновлений панели (WebSocket)."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

CHANNEL = "avito:events"


async def publish(redis: Redis, event_type: str, **payload: Any) -> None:
    """Публикует событие; ошибки не должны ломать основной сценарий."""
    message = json.dumps(
        {
            "type": event_type,
            "payload": payload,
            "ts": datetime.now(UTC).isoformat(),
        },
        ensure_ascii=False,
        default=str,
    )
    try:
        await redis.publish(CHANNEL, message)
    except Exception as error:  # noqa: BLE001 — live не критичен для работы
        logger.warning("event publish failed (%s): %s", event_type, error)
