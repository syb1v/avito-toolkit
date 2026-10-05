"""Watchdog: алерты в UI, когда воркер не отвечает или очередь забита."""

import logging
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Alert
from app.services.health_alerts import (
    ACCOUNT_STALE,
    AI_BALANCE_LOW,
    PROXY_DEAD,
    check_accounts,
    check_ai_balance,
    check_proxies,
)
from app.services.queues import queue_depth, worker_alive

logger = logging.getLogger(__name__)

WORKER_DOWN = "worker_down"
QUEUE_BACKLOG = "queue_backlog"


async def _has_open(session: AsyncSession, alert_type: str) -> bool:
    found = await session.scalar(
        select(Alert.id).where(Alert.type == alert_type, Alert.status == "new").limit(1)
    )
    return found is not None


async def _resolve_open(session: AsyncSession, alert_type: str) -> None:
    await session.execute(
        update(Alert).where(Alert.type == alert_type, Alert.status == "new").values(status="acked")
    )


async def _sync_system_alert(
    session: AsyncSession,
    alert_type: str,
    payload: dict[str, object],
    problem: bool,
) -> None:
    if problem:
        if not await _has_open(session, alert_type):
            session.add(Alert(type=alert_type, payload=payload, status="new"))
            logger.warning("watchdog: %s (%s)", alert_type, payload.get("reason"))
    else:
        await _resolve_open(session, alert_type)


async def run_watchdog(session: AsyncSession, redis: Redis) -> dict[str, object]:
    """Одна проверка: воркер жив? очередь не забита? Создаёт/закрывает алерты."""
    settings = get_settings()
    alive = await worker_alive(redis, window_seconds=settings.worker_alive_window_seconds)
    crawl_queue = await queue_depth(redis, "dramatiq:crawl")
    analytics_queue = await queue_depth(redis, "dramatiq:analytics")
    total_queue = crawl_queue + analytics_queue

    if alive:
        await _resolve_open(session, WORKER_DOWN)
    elif not await _has_open(session, WORKER_DOWN):
        session.add(
            Alert(
                type=WORKER_DOWN,
                payload={
                    "kind": "worker_down",
                    "queue_depth": total_queue,
                    "checked_at": datetime.now(UTC).isoformat(),
                },
                status="new",
            )
        )
        logger.error("watchdog: воркер не отвечает, очередь %s", total_queue)

    if alive and total_queue >= settings.watchdog_queue_warn_depth:
        if not await _has_open(session, QUEUE_BACKLOG):
            session.add(
                Alert(
                    type=QUEUE_BACKLOG,
                    payload={
                        "kind": "queue_backlog",
                        "queue_depth": total_queue,
                        "crawl_queue": crawl_queue,
                        "analytics_queue": analytics_queue,
                        "checked_at": datetime.now(UTC).isoformat(),
                    },
                    status="new",
                )
            )
            logger.warning("watchdog: очередь забита (%s)", total_queue)
    else:
        await _resolve_open(session, QUEUE_BACKLOG)

    checked_at = datetime.now(UTC).isoformat()
    stale_accounts = await check_accounts(session, settings)
    await _sync_system_alert(
        session,
        ACCOUNT_STALE,
        {"kind": ACCOUNT_STALE, "accounts": stale_accounts, "checked_at": checked_at},
        bool(stale_accounts),
    )
    proxy_problem = await check_proxies(redis, session, settings)
    await _sync_system_alert(
        session,
        PROXY_DEAD,
        {"kind": PROXY_DEAD, **(proxy_problem or {}), "checked_at": checked_at},
        proxy_problem is not None,
    )
    balance = await check_ai_balance(settings)
    await _sync_system_alert(
        session,
        AI_BALANCE_LOW,
        {"kind": AI_BALANCE_LOW, **(balance or {}), "checked_at": checked_at},
        bool(balance and balance.get("low")),
    )

    await session.flush()
    return {
        "worker_alive": alive,
        "crawl_queue": crawl_queue,
        "analytics_queue": analytics_queue,
        "accounts_stale": len(stale_accounts),
        "proxy_dead": proxy_problem,
        "ai_balance": balance,
    }
