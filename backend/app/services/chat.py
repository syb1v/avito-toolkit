"""Чат-ассистент: планирование инструментов и ответ человеческим языком."""

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LlmResult, complete_structured
from app.ai.prompts import (
    CHAT_ANSWER_VERSION,
    CHAT_PLAN_VERSION,
    build_chat_answer_prompt,
    build_chat_plan_prompt,
)
from app.ai.runs import record_llm_run
from app.ai.schemas import ChatAnswer, ChatPlan
from app.config import get_settings
from app.db.models import AiArtifact, Alert, Listing, ListingEdit, LlmRun, OurListing, Search
from app.services.analytics.service import build_search_summary
from app.services.queues import system_health
from app.services.recommendations import build_recommendations

logger = logging.getLogger(__name__)

TOOL_DESCRIPTIONS: dict[str, str] = {
    "system_overview": (
        "общая сводка по системе: поиски, объявления, алерты, очередь, расходы AI, баланс"
    ),
    "list_searches": "список поисков со статусом и количеством объявлений",
    "search_market": (
        "рынок по конкретному поиску: медиана, перцентили, активные, новые, снятые, дайджест"
    ),
    "our_listings": "наши товары: цены, медианы, отклонения от рынка",
    "recommendations": "текущие рекомендации по ценам (что и на сколько менять)",
    "alerts_new": "новые уведомления (алерты)",
    "edits_recent": "последние правки цен и их статусы",
    "ai_spend": "расходы на AI: сутки, месяц, по задачам",
}

ACTION_LABELS: dict[str, str] = {
    "crawl": "Запустить обход поиска",
    "digest": "Сгенерировать дайджест по поиску",
    "clear_alerts": "Отметить все алерты прочитанными",
    "manual_edit": "Поставить свою цену товару",
}


async def _tool_system_overview(session: AsyncSession, redis: Redis, **_: Any) -> dict[str, Any]:
    settings = get_settings()
    health = await system_health(redis, window_seconds=settings.worker_alive_window_seconds)
    totals = {
        "searches_active": int(
            await session.scalar(select(func.count()).select_from(Search).where(Search.is_active))
            or 0
        ),
        "searches_total": int(await session.scalar(select(func.count()).select_from(Search)) or 0),
        "listings_active": int(
            await session.scalar(
                select(func.count()).select_from(Listing).where(Listing.status == "active")
            )
            or 0
        ),
        "our_listings": int(
            await session.scalar(
                select(func.count())
                .select_from(OurListing)
                .where(OurListing.is_active, OurListing.account_id.is_not(None))
            )
            or 0
        ),
        "alerts_new": int(
            await session.scalar(
                select(func.count()).select_from(Alert).where(Alert.status == "new")
            )
            or 0
        ),
        "worker_alive": bool(health.get("worker_alive")),
        "queues": {"crawl": health.get("crawl_queue"), "analytics": health.get("analytics_queue")},
    }
    costs = await session.execute(
        select(
            func.coalesce(func.sum(LlmRun.cost_usd), 0),
        )
    )
    totals["ai_spend_total_usd"] = round(float(costs.scalar() or 0), 4)
    balance_raw = await redis.get("ai:balance:v1")
    if balance_raw:
        try:
            balance = json.loads(balance_raw)
            totals["ai_balance"] = {
                "value": balance.get("balance"),
                "currency": balance.get("currency"),
            }
        except (TypeError, ValueError):
            pass
    return totals


async def _tool_list_searches(session: AsyncSession, **_: Any) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(Search.id, Search.name, Search.is_active, Search.schedule_cron).order_by(Search.name)
    )
    counts = await session.execute(
        select(Search.id, func.count(Listing.id))
        .join(Listing, Listing.status == "active", isouter=True)
        .group_by(Search.id)
    )
    count_map = {row[0]: int(row[1] or 0) for row in counts.all()}
    return [
        {
            "id": str(row[0]),
            "name": row[1],
            "active": bool(row[2]),
            "listings": count_map.get(row[0], 0),
            "schedule": row[3],
        }
        for row in rows.all()
    ]


def _find_search(searches: list[Search], query: str | None) -> Search | None:
    if not searches:
        return None
    if not query:
        return searches[0]
    needle = query.strip().lower()
    for search in searches:
        if search.name.lower() == needle:
            return search
    for search in searches:
        if needle in search.name.lower():
            return search
    try:
        target = uuid.UUID(query)
    except (ValueError, AttributeError):
        return None
    for search in searches:
        if search.id == target:
            return search
    return None


async def _tool_search_market(
    session: AsyncSession, *, search: str | None = None, **_: Any
) -> dict[str, Any]:
    searches = list(
        (await session.execute(select(Search).order_by(Search.priority, Search.name))).scalars()
    )
    found = _find_search(searches, search)
    if found is None:
        return {"error": "поиск не найден", "available": [s.name for s in searches[:10]]}
    summary = await build_search_summary(session, found.id)
    stats = summary.stats
    digest = await session.execute(
        select(AiArtifact.payload, AiArtifact.created_at)
        .where(AiArtifact.kind == "digest", AiArtifact.key == str(found.id))
        .order_by(AiArtifact.created_at.desc())
        .limit(1)
    )
    digest_row = digest.first()
    return {
        "search": found.name,
        "active": summary.active_count,
        "new_today": summary.new_today_count,
        "delisted_today": summary.delisted_today_count,
        "median": stats.median if stats else None,
        "p25": stats.p25 if stats else None,
        "p75": stats.p75 if stats else None,
        "last_digest_headline": (digest_row[0] or {}).get("headline") if digest_row else None,
    }


async def _tool_our_listings(session: AsyncSession, **_: Any) -> list[dict[str, Any]]:
    from app.services.matching import build_overview

    rows = await build_overview(session)
    rows.sort(
        key=lambda row: abs(row.delta_to_median_pct or 0),
        reverse=True,
    )
    return [
        {
            "sku": row.sku,
            "title": row.title,
            "price": row.our_price,
            "market_median": row.market_median,
            "delta_pct": row.delta_to_median_pct,
            "matched": row.matched_count,
        }
        for row in rows[:12]
    ]


async def _tool_recommendations(session: AsyncSession, **_: Any) -> list[dict[str, Any]]:
    return [
        {
            "sku": rec.sku,
            "title": rec.title,
            "price": rec.our_price,
            "target": rec.clamped_price,
            "delta_pct": round(rec.delta_pct, 2),
            "strategy": rec.strategy,
        }
        for rec in (await build_recommendations(session))[:12]
    ]


async def _tool_alerts_new(session: AsyncSession, **_: Any) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(Alert).where(Alert.status == "new").order_by(Alert.created_at.desc()).limit(10)
    )
    return [
        {
            "type": alert.type,
            "title": (alert.payload or {}).get("title"),
            "at": str(alert.created_at),
        }
        for alert in rows.scalars()
    ]


async def _tool_edits_recent(session: AsyncSession, **_: Any) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(ListingEdit).order_by(ListingEdit.created_at.desc()).limit(10)
    )
    return [
        {
            "sku": edit.sku,
            "status": edit.status,
            "old": float(edit.old_price),
            "target": float(edit.target_price),
            "reason": (edit.ai_summary or "")[:140],
        }
        for edit in rows.scalars()
    ]


async def _tool_ai_spend(session: AsyncSession, **_: Any) -> dict[str, Any]:
    by_task = await session.execute(
        select(LlmRun.task, func.count(), func.coalesce(func.sum(LlmRun.cost_usd), 0))
        .group_by(LlmRun.task)
        .order_by(func.coalesce(func.sum(LlmRun.cost_usd), 0).desc())
    )
    total = await session.scalar(select(func.coalesce(func.sum(LlmRun.cost_usd), 0)))
    return {
        "total_usd": round(float(total or 0), 4),
        "by_task": [
            {"task": row[0], "runs": int(row[1]), "cost_usd": round(float(row[2] or 0), 4)}
            for row in by_task.all()
        ],
    }


TOOLS: dict[str, Callable[..., Awaitable[Any]]] = {
    "system_overview": _tool_system_overview,
    "list_searches": _tool_list_searches,
    "search_market": _tool_search_market,
    "our_listings": _tool_our_listings,
    "recommendations": _tool_recommendations,
    "alerts_new": _tool_alerts_new,
    "edits_recent": _tool_edits_recent,
    "ai_spend": _tool_ai_spend,
}


def tool_catalog() -> str:
    return "\n".join(f"- {name}: {description}" for name, description in TOOL_DESCRIPTIONS.items())


async def run_tools(
    names: list[str],
    *,
    session: AsyncSession,
    redis: Redis,
    search: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Выполняет выбранные инструменты, возвращает (трейс, данные)."""
    trace: list[dict[str, Any]] = []
    data: dict[str, Any] = {}
    for name in names[:5]:
        handler = TOOLS.get(name)
        if handler is None:
            continue
        try:
            result = await handler(session, redis, search=search)
        except Exception as error:  # noqa: BLE001 — чат не должен падать
            logger.warning("chat tool %s failed: %s", name, error)
            trace.append({"name": name, "ok": False, "error": str(error)[:120]})
            continue
        data[name] = result
        trace.append({"name": name, "ok": True})
    return trace, data


async def plan_message(
    session: AsyncSession,
    *,
    text: str,
    history: list[tuple[str, str]],
) -> LlmResult[ChatPlan]:
    result = await complete_structured(
        ChatPlan,
        system_prompt=(
            "Ты планировщик AI-ассистента панели Avito Toolkit. Выбери, какие данные нужны, "
            "чтобы ответить. Не выдумывай инструменты. Если пользователь просит действие "
            "(запустить обход, дайджест, очистить алерты, поставить свою цену) — заполни "
            "action_type и связанные поля; это выполнится ТОЛЬКО после подтверждения человеком. "
            "Если данных достаточно без инструментов — оставь список пустым."
        ),
        user_prompt=build_chat_plan_prompt(
            text=text, history=history, tools=tool_catalog(), actions=list(ACTION_LABELS)
        ),
        task="chat",
        prompt_version=CHAT_PLAN_VERSION,
    )
    await record_llm_run(session, task="chat", result=result, prompt_version=CHAT_PLAN_VERSION)
    return result


async def answer_message(
    session: AsyncSession,
    *,
    text: str,
    history: list[tuple[str, str]],
    tool_data: dict[str, Any],
) -> LlmResult[ChatAnswer]:
    result = await complete_structured(
        ChatAnswer,
        system_prompt=(
            "Ты полезный ассистент владельца магазина на Авито. Отвечай простым человеческим "
            "языком, коротко (2–6 предложений, можно списком). Опирайся только на переданные "
            "данные, числа приводи с ₽. Без технического жаргона и английских кодов."
        ),
        user_prompt=build_chat_answer_prompt(text=text, history=history, tool_data=tool_data),
        task="chat",
        prompt_version=CHAT_ANSWER_VERSION,
        max_tokens=1200,
    )
    await record_llm_run(session, task="chat", result=result, prompt_version=CHAT_ANSWER_VERSION)
    return result
