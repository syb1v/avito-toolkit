"""Оркестратор субагентов: параллельные агенты категорий → консенсус → решения.

Агенты запускаются каждый со своей сессией (параллельно, с ограничением),
затем один вызов LLM собирает единый план по ценам. План сохраняется как
«предложение» (agent_decisions) и применяется только после подтверждения человеком.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.client import LlmNotConfiguredError, complete_structured
from app.ai.prompts import CONSENSUS_VERSION, build_consensus_prompt
from app.ai.runs import record_llm_run
from app.ai.schemas import ConsensusPlan
from app.config import get_settings
from app.db.models import AgentDecision, AgentPlaybook, OurListing
from app.db.session import dispose_engine, get_engine
from app.services.agents import run_agent
from app.services.ai_center import save_artifact
from app.services.events import publish

logger = logging.getLogger(__name__)

MAX_PARALLEL_AGENTS = 3


async def _run_one(playbook_id: str) -> dict[str, Any] | None:
    factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    redis = Redis.from_url(get_settings().redis_url)
    try:
        async with factory() as session:
            playbook = await session.get(AgentPlaybook, playbook_id)
            if playbook is None:
                return None
            return await run_agent(session, redis, playbook)
    except Exception as error:  # noqa: BLE001 — один агент упал, остальные едем
        logger.warning("subagent %s failed: %s", playbook_id, error)
        return None
    finally:
        await redis.aclose()
        await dispose_engine()


async def run_orchestrator(session: AsyncSession, redis: Redis) -> dict[str, Any]:
    """Параллельный прогон агентов и сборка консенсуса (предложение человеку)."""
    playbooks = list(
        (
            await session.execute(select(AgentPlaybook).where(AgentPlaybook.is_active.is_(True)))
        ).scalars()
    )
    if not playbooks:
        raise RuntimeError("нет активных плейбуков — добавьте категории")
    semaphore = asyncio.Semaphore(MAX_PARALLEL_AGENTS)

    async def limited(playbook: AgentPlaybook) -> dict[str, Any] | None:
        async with semaphore:
            return await _run_one(str(playbook.id))

    reports = [
        report for report in await asyncio.gather(*(limited(p) for p in playbooks)) if report
    ]
    if not reports:
        raise RuntimeError("агенты не дали отчётов (проверьте ключ AI и плейбуки)")

    our_rows = (
        (
            await session.execute(
                select(OurListing)
                .where(OurListing.is_active.is_(True), OurListing.account_id.is_not(None))
                .limit(200)
            )
        )
        .scalars()
        .all()
    )
    our_items = "\n".join(
        f"- {row.sku}: {row.title[:80]} — {float(row.price):.0f} ₽" for row in our_rows[:60]
    )
    reports_json = json.dumps(
        [
            {
                "playbook": report.get("playbook"),
                "headline": report.get("headline"),
                "price_actions": report.get("price_actions"),
                "risks": report.get("risks"),
                "sources": report.get("sources") or [],
            }
            for report in reports
        ],
        ensure_ascii=False,
        default=str,
    )[:9000]
    try:
        consensus = await complete_structured(
            ConsensusPlan,
            system_prompt=(
                "Ты главный аналитик: сводишь отчёты агентов категорий в единый безопасный "
                "план по ценам наших товаров. Только реальные SKU из списка, числа в рублях. "
                "Простой человеческий язык, без технических кодов."
            ),
            user_prompt=build_consensus_prompt(reports=reports_json, our_items=our_items),
            task="consensus",
            prompt_version=CONSENSUS_VERSION,
            max_tokens=1600,
        )
    except LlmNotConfiguredError as error:
        raise RuntimeError(str(error)) from error
    await record_llm_run(
        session, task="consensus", result=consensus, prompt_version=CONSENSUS_VERSION
    )
    by_sku = {row.sku: row for row in our_rows}
    items: list[dict[str, Any]] = []
    for item in consensus.content.items:
        listing = by_sku.get(item.sku)
        if listing is None:
            continue
        current = float(listing.price)
        delta_pct = 0.0 if current <= 0 else (item.price - current) / current * 100
        items.append(
            {
                "sku": item.sku,
                "title": listing.title,
                "current_price": current,
                "suggested_price": round(item.price, 2),
                "delta_pct": round(delta_pct, 2),
                "confidence": item.confidence,
                "reason": item.reason,
                "source": report_source(reports, item.sku),
            }
        )
    payload = {
        "headline": consensus.content.headline,
        "items": items,
        "agents": [report.get("playbook", {}).get("name") for report in reports],
        "sources": [
            source
            for report in reports
            for source in (report.get("sources") or [])
            if isinstance(source, dict) and source.get("url")
        ],
        "at": datetime.now(UTC).isoformat(),
    }
    decision = AgentDecision(status="proposed", payload=payload)
    session.add(decision)
    await session.flush()
    await save_artifact(
        session,
        kind="consensus",
        key=str(decision.id),
        payload=payload,
        model=consensus.model,
        cost_usd=consensus.cost_usd,
    )
    await session.commit()
    await publish(
        redis,
        "agent.consensus",
        decision_id=str(decision.id),
        headline=payload["headline"],
        items=len(items),
    )
    return {"decision_id": str(decision.id), **payload}


def report_source(reports: list[dict[str, Any]], sku: str) -> str | None:
    """Категория/агент, предложивший цену по SKU (для журнала решений)."""
    for report in reports:
        for action in report.get("price_actions") or []:
            if isinstance(action, dict) and action.get("sku") == sku:
                return str(report.get("playbook", {}).get("name") or report.get("playbook"))
    return None
