"""Агенты рынка по категориям: плейбуки владельца → структурированный отчёт.

Готово к локальному рантайму: агент использует тот же LLM-клиент, который
переключается на локальный endpoint переменными LLM_LOCAL_BASE_URL/MODEL.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LlmNotConfiguredError, complete_structured
from app.ai.prompts import AGENT_REPORT_VERSION, build_agent_prompt
from app.ai.runs import record_llm_run
from app.ai.schemas import AgentReport
from app.db.models import AgentPlaybook, ListingEdit, Search
from app.services.ai_center import save_artifact
from app.services.events import publish
from app.services.facets import listing_brand
from app.services.web_research import research_product_identity

logger = logging.getLogger(__name__)


async def collect_research(items: list[dict[str, Any]]) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    for item in items[:3]:
        result = await research_product_identity(str(item["title"]))
        for source in result.sources:
            sources.append(
                {
                    "sku": item["sku"],
                    "url": source.url,
                    "title": source.title,
                    "retrieved_at": source.retrieved_at.isoformat(),
                    "claim": "Поисковый результат; содержимое страницы ещё не проверено",
                    "verified": False,
                }
            )
    return {"status": "sources_found" if sources else "needs_review", "sources": sources}


def constrain_agent_output(payload: dict[str, Any], data: dict[str, Any]) -> None:
    allowed = {item["sku"] for item in data["our_items"]}
    payload["price_actions"] = [
        action for action in payload.get("price_actions", []) if action.get("sku") in allowed
    ]
    # Sources are supplied by the retrieval layer, never authored by the model.
    payload["sources"] = data["research"]["sources"]
    payload["input_snapshot"] = data
    payload.setdefault("risks", []).append(
        "Веб-результаты — ссылки для проверки, а не подтверждённые характеристики моделей."
    )


def _criteria_text(criteria: dict) -> str:
    lines: list[str] = []
    for key, value in criteria.items():
        if isinstance(value, list):
            lines.append(f"- {key}: {', '.join(str(item) for item in value)}")
        else:
            lines.append(f"- {key}: {value}")
    return "\n".join(lines) or "- критерии не заданы"


async def collect_category_data(session: AsyncSession, playbook: AgentPlaybook) -> dict[str, Any]:
    """Данные категории: поиски (по ключевым словам), рынок, наши цены, правки."""
    from app.services.analytics.service import build_search_summary

    keywords = [
        playbook.category.lower(),
        *[str(k).lower() for k in (playbook.criteria or {}).get("keywords", [])],
    ]
    searches = list((await session.execute(select(Search))).scalars())
    matched = [s for s in searches if any(word in s.name.lower() for word in keywords if word)]
    markets = []
    for search in matched[:4]:
        summary = await build_search_summary(session, search.id)
        stats = summary.stats
        markets.append(
            {
                "search": search.name,
                "active": summary.active_count,
                "new_today": summary.new_today_count,
                "delisted_today": summary.delisted_today_count,
                "median": stats.median if stats else None,
                "p25": stats.p25 if stats else None,
                "p75": stats.p75 if stats else None,
            }
        )
    from app.db.models import OurListing

    our_rows = list(
        (
            await session.execute(
                select(OurListing).where(OurListing.is_active, OurListing.account_id.is_not(None))
            )
        ).scalars()
    )
    brand_key = (playbook.criteria or {}).get("brand")
    ours = []
    for listing in our_rows:
        if brand_key:
            local_brand = listing_brand(
                listing.title,
                {"ai_tags": (listing.params or {}).get("ai_tags")}
                if isinstance(listing.params, dict)
                else None,
            )
            if local_brand and str(local_brand).lower() != str(brand_key).lower():
                continue
        ours.append({"sku": listing.sku, "title": listing.title, "price": float(listing.price)})
    edits = list(
        (
            await session.execute(
                select(ListingEdit).order_by(ListingEdit.created_at.desc()).limit(10)
            )
        ).scalars()
    )
    return {
        "markets": markets,
        "our_items": ours[:20],
        "recent_edits": [
            {
                "sku": edit.sku,
                "status": edit.status,
                "old": float(edit.old_price),
                "target": float(edit.target_price),
            }
            for edit in edits
        ],
    }


async def run_agent(session: AsyncSession, redis: Redis, playbook: AgentPlaybook) -> dict[str, Any]:
    """Прогон агента: данные категории + плейбук → отчёт, сохранённый как артефакт."""
    data = await collect_category_data(session, playbook)
    data["research"] = await collect_research(data["our_items"])
    try:
        result = await complete_structured(
            AgentReport,
            system_prompt=(
                "Ты агент рынка Авито по категории. Опирайся только на данные и критерии "
                "владельца. Пиши простым человеческим языком, без технических кодов. "
                "Дай сводку рынка, предложения по ценам наших товаров (можно с обоснованием) "
                "и риски. Если данных мало — честно скажи об этом. Не выдумывай источники: "
                "если веб-источников нет, верни sources пустым и укажи неопределённость."
            ),
            user_prompt=build_agent_prompt(
                name=playbook.name,
                category=playbook.category,
                criteria=_criteria_text(playbook.criteria or {}),
                data=json.dumps(data, ensure_ascii=False, default=str)[:8000],
            ),
            task="agent",
            prompt_version=AGENT_REPORT_VERSION,
            max_tokens=1600,
        )
    except LlmNotConfiguredError as error:
        raise RuntimeError(str(error)) from error
    await record_llm_run(session, task="agent", result=result, prompt_version=AGENT_REPORT_VERSION)
    payload = result.content.model_dump(mode="json")
    constrain_agent_output(payload, data)
    payload["at"] = datetime.now(UTC).isoformat()
    payload["playbook"] = {
        "id": str(playbook.id),
        "name": playbook.name,
        "category": playbook.category,
    }
    await save_artifact(
        session,
        kind="agent_report",
        key=str(playbook.id),
        payload=payload,
        model=result.model,
        cost_usd=result.cost_usd,
    )
    await session.commit()
    await publish(
        redis,
        "agent.report",
        playbook_id=str(playbook.id),
        name=playbook.name,
        headline=payload.get("headline", ""),
    )
    return payload
