"""Умная фильтрация выдачи: стоп-слова, аномальные цены, дубли и AI-скоринг."""

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LlmNotConfiguredError
from app.ai.prompts import MODERATION_VERSION
from app.ai.runs import record_llm_run
from app.ai.tasks import moderate_listings_batch
from app.config import get_settings
from app.db.models import Listing, Search, SearchListing
from app.services.analytics.iqr import compute_price_stats

logger = logging.getLogger(__name__)

WORD_SPLIT = re.compile(r"[^0-9a-zа-яё]+")

COPY_WORDS = (
    "копия",
    "копія",
    "реплика",
    "подделка",
    "аналог",
    "1:1",
    "aa+",
    "aaa",
    "люкс",
    "суперкопия",
)
JUNK_WORDS = (
    "запчаст",
    "разбор",
    "нерабоч",
    "не работает",
    "битый",
    "восстановлен",
    "на ремонт",
)
SOFT_WORDS = ("торг", "срочно", "обмен", "приманка")


@dataclass(frozen=True, slots=True)
class Verdict:
    flagged: bool
    reasons: list[str]
    score: float


@dataclass(frozen=True, slots=True)
class ModerationResult:
    total: int
    flagged: int
    ai_scored: int
    median: float | None


def normalize_title(title: str) -> str:
    lowered = title.lower().replace("ё", "е")
    words = [word for word in WORD_SPLIT.split(lowered) if word]
    return " ".join(words)


def detect_clusters(
    rows: list[tuple[int, str, float | None, int | None]],
) -> dict[int, int]:
    """Кластеры «одинаковое название + одинаковая цена» от разных продавцов.

    Возвращает listing_id -> размер кластера (для одиночек не включается).
    """
    groups: dict[tuple[str, int], set[int | None]] = defaultdict(set)
    members: dict[tuple[str, int], list[int]] = defaultdict(list)
    for listing_id, title, price, seller_id in rows:
        if price is None:
            continue
        key = (normalize_title(title), int(price))
        groups[key].add(seller_id)
        members[key].append(listing_id)
    clusters: dict[int, int] = {}
    for key, listing_ids in members.items():
        distinct_sellers = len({seller for seller in groups[key] if seller is not None})
        if distinct_sellers >= 3:
            for listing_id in listing_ids:
                clusters[listing_id] = len(listing_ids)
    return clusters


def evaluate_listing(
    title: str,
    price: float | None,
    median: float | None,
    cluster_size: int,
    *,
    low_price_ratio: float = 0.35,
    duplicate_min_cluster: int = 5,
) -> Verdict:
    """Детерминированные признаки копии/нерелеванта/приманки."""
    lowered = title.lower().replace("ё", "е")
    reasons: list[str] = []
    score = 0.0

    if any(word in lowered for word in COPY_WORDS):
        reasons.append("копия/реплика в названии")
        score = max(score, 0.9)
    if any(word in lowered for word in JUNK_WORDS):
        reasons.append("запчасти/нерелевант")
        score = max(score, 0.75)
    if price is not None and median and median > 0 and price < median * low_price_ratio:
        reasons.append(f"цена ниже {int(low_price_ratio * 100)}% медианы")
        score = max(score, 0.6)
    if cluster_size >= duplicate_min_cluster:
        reasons.append(f"дубли: {cluster_size} объявлений с той же ценой")
        score = max(score, 0.55)

    soft = [word for word in SOFT_WORDS if word in lowered]
    if soft:
        reasons.append("маркетинг: " + ", ".join(soft))

    flagged = score >= 0.5
    return Verdict(flagged=flagged, reasons=reasons, score=round(score, 3))


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


async def moderate_search(
    session: AsyncSession, search_id: Any, *, ai: bool | None = None
) -> ModerationResult:
    """Прогон модерации по активной выдаче поиска; флаги пишутся в listings."""
    settings = get_settings()
    if not settings.moderation_enabled:
        return ModerationResult(total=0, flagged=0, ai_scored=0, median=None)

    search = await session.get(Search, search_id)
    rows = (
        await session.execute(
            select(
                Listing.id,
                Listing.title,
                Listing.current_price,
                Listing.seller_id,
            )
            .join(SearchListing, SearchListing.listing_id == Listing.id)
            .where(SearchListing.search_id == search_id, Listing.status == "active")
        )
    ).all()
    listing_rows: list[tuple[int, str, float | None, int | None]] = [
        (
            row[0],
            row[1],
            float(row[2]) if row[2] is not None else None,
            row[3],
        )
        for row in rows
    ]
    prices = [row[2] for row in listing_rows if row[2] is not None]
    median = float(compute_price_stats(prices).median) if prices else None
    clusters = detect_clusters(listing_rows)

    now = datetime.now(UTC)
    verdicts: dict[int, Verdict] = {}
    candidates: list[tuple[int, str, float | None, int | None]] = []
    for listing_id, title, price, seller_id in listing_rows:
        verdict = evaluate_listing(
            title,
            price,
            median,
            clusters.get(listing_id, 0),
            low_price_ratio=settings.moderation_low_price_ratio,
            duplicate_min_cluster=settings.moderation_duplicate_min_cluster,
        )
        verdicts[listing_id] = verdict
        near_threshold = (
            price is not None
            and median is not None
            and price < median * settings.moderation_ai_candidate_ratio
        )
        if verdict.flagged or near_threshold:
            candidates.append((listing_id, title, price, seller_id))

    for listing_id, verdict in verdicts.items():
        await session.execute(
            update(Listing)
            .where(Listing.id == listing_id)
            .values(
                is_flagged=verdict.flagged,
                flag_reasons=verdict.reasons or None,
                relevance_score=verdict.score,
                moderated_at=now,
            )
        )

    use_ai = settings.moderation_ai_enabled if ai is None else ai
    ai_scored = 0
    if use_ai and candidates and median is not None and settings.deepseek_api_key:
        limited = candidates[: settings.moderation_max_ai_items]
        for batch in _chunks(limited, settings.moderation_ai_batch_size):
            try:
                result = await moderate_listings_batch(
                    query=search.name if search is not None else "",
                    median=median,
                    items=[(item[0], item[1], item[2]) for item in batch],
                )
            except LlmNotConfiguredError:
                break
            except Exception as error:
                logger.warning("AI moderation failed: %s", error)
                break
            await record_llm_run(
                session,
                task="listing_moderation",
                result=result,
                prompt_version=MODERATION_VERSION,
            )
            ai_scored += len(result.content.items)
            for decision in result.content.items:
                existing = verdicts.get(decision.listing_id)
                if existing is None:
                    continue
                merged_reasons = list(existing.reasons)
                if decision.reason:
                    merged_reasons.append(f"AI: {decision.reason}")
                flagged = existing.flagged or (
                    decision.likely_fake_or_copy and not decision.relevant
                )
                score = max(existing.score, decision.confidence if flagged else 0.0)
                await session.execute(
                    update(Listing)
                    .where(Listing.id == decision.listing_id)
                    .values(
                        is_flagged=flagged,
                        flag_reasons=merged_reasons or None,
                        relevance_score=round(score, 3),
                        moderated_at=now,
                    )
                )
                verdicts[decision.listing_id] = Verdict(
                    flagged=flagged, reasons=merged_reasons, score=round(score, 3)
                )

    await session.flush()
    return ModerationResult(
        total=len(listing_rows),
        flagged=sum(1 for verdict in verdicts.values() if verdict.flagged),
        ai_scored=ai_scored,
        median=median,
    )
