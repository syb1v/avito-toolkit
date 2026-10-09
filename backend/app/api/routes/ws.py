"""WebSocket-канал live-событий панели (Redis pub/sub fanout)."""

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis
from starlette.websockets import WebSocketState

from app.config import get_settings
from app.services.events import CHANNEL

logger = logging.getLogger(__name__)

router = APIRouter(tags=["events"])


@router.websocket("/ws")
async def ws_events(websocket: WebSocket) -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    pubsub = redis.pubsub()
    await websocket.accept()
    try:
        await pubsub.subscribe(CHANNEL)
        await websocket.send_text(json.dumps({"type": "hello"}))

        async def forward() -> None:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = message.get("data")
                text = data.decode() if isinstance(data, bytes) else str(data)
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text(text)

        task = asyncio.create_task(forward())
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    except Exception as error:  # noqa: BLE001 — WS не должен ронять приложение
        logger.warning("ws session failed: %s", error)
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()
        await redis.aclose()
