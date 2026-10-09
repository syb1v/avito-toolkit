"""Фацеты объявлений: бренды для фильтров и «дайджеста по бренду».

Бренд определяется AI-тегами (кэш в Listing.params["ai_tags"]) или словарём.
"""

import hashlib
import logging
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import FACETS_VERSION
from app.ai.runs import record_llm_run
from app.ai.tasks import tag_listings_batch
from app.config import get_settings
from app.db.models import Listing, SearchListing

logger = logging.getLogger(__name__)

BRAND_DICTIONARY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Bang & Olufsen", ("bang olufsen", "bang&olufsen", "b&o", "beoplay", "beosound", "beolab")),
    ("Devialet", ("devialet",)),
    ("Apple", ("apple", "iphone", "ipad", "macbook", "airpods", "watch ultra")),
    ("Insta360", ("insta360",)),
    ("Garmin", ("garmin", "fenix", "forerunner")),
    ("Leica", ("leica",)),
    ("Sony", ("sony", "playstation")),
    ("Dyson", ("dyson",)),
    ("DJI", ("dji",)),
    ("GoPro", ("gopro",)),
    ("Samsung", ("samsung", "galaxy")),
    ("Xiaomi", ("xiaomi", "redmi", "poco")),
)


def title_hash(title: str) -> str:
    return hashlib.sha1(title.strip().lower().encode("utf-8")).hexdigest()[:12]


def brand_from_dictionary(title: str) -> str | None:
    lowered = title.lower().replace("ё", "е")
    for brand, keys in BRAND_DICTIONARY:
        if any(key in lowered for key in keys):
            return brand
    return None


def listing_brand(title: str, params: dict | None) -> str | None:
    if isinstance(params, dict):
        tags = params.get("ai_tags")
        if (
            isinstance(tags, dict)
            and tags.get("brand")
            and tags.get("title_hash") == title_hash(title)
        ):
            brand = str(tags["brand"]).strip()
            if brand and brand.lower() not in ("неизвестно", "unknown", "другое"):
                return brand
    return brand_from_dictionary(title)


async def tag_search_listings(
    session: AsyncSession, search_id: Any, max_items: int | None = None
) -> int:
    """AI-разметка бренда/модели/цвета для активных объявлений поиска (с кэшем)."""
    settings = get_settings()
    if not settings.facets_ai_enabled or not settings.deepseek_api_key:
        return 0
    limit = max_items or settings.facets_ai_max_items
    rows = (
        await session.execute(
            select(Listing.id, Listing.title, Listing.params)
            .join(SearchListing, SearchListing.listing_id == Listing.id)
            .where(SearchListing.search_id == search_id, Listing.status == "active")
            .limit(500)
        )
    ).all()
    pending: list[tuple[int, str]] = []
    for listing_id, title, params in rows:
        tags = params.get("ai_tags") if isinstance(params, dict) else None
        if isinstance(tags, dict) and tags.get("title_hash") == title_hash(title or ""):
            continue
        if title:
            pending.append((listing_id, title))
    pending = pending[:limit]
    if not pending:
        return 0
    tagged = 0
    batch_size = settings.facets_ai_batch_size
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        try:
            result = await tag_listings_batch(items=batch)
        except Exception as error:  # noqa: BLE001 — разметка не критична для обхода
            logger.warning("facets tagging failed: %s", error)
            break
        await record_llm_run(session, task="facets", result=result, prompt_version=FACETS_VERSION)
        by_id = {item.listing_id: item for item in result.content.items}
        for listing_id, title in batch:
            item = by_id.get(listing_id)
            if item is None:
                continue
            current = (
                await session.execute(select(Listing.params).where(Listing.id == listing_id))
            ).scalar()
            params = dict(current) if isinstance(current, dict) else {}
            params["ai_tags"] = {
                "brand": item.brand.strip(),
                "model": item.model.strip(),
                "color": item.color.strip(),
                "title_hash": title_hash(title),
            }
            await session.execute(
                update(Listing).where(Listing.id == listing_id).values(params=params)
            )
            tagged += 1
    return tagged


async def search_facets(session: AsyncSession, search_id: Any, limit: int = 12) -> list[dict]:
    """Бренды выдачи поиска с количеством (по активным объявлениям)."""
    from app.services.analytics.service import _filtered_listings

    rows = await _filtered_listings(session, search_id)
    counts: dict[str, int] = {}
    for row in rows:
        if row.reason is not None or not row.brand:
            continue
        counts[row.brand] = counts.get(row.brand, 0) + 1
    ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return [{"brand": brand, "count": count} for brand, count in ordered[:limit]]
