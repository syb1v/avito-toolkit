"""Умная фильтрация выдачи: стоп-слова, аномальные цены, дубли, описания и AI-скоринг."""

import asyncio
import logging
import random
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LlmNotConfiguredError
from app.ai.prompts import DESCRIPTION_REVIEW_VERSION, MODERATION_VERSION
from app.ai.runs import record_llm_run
from app.ai.tasks import moderate_listings_batch, review_descriptions_batch
from app.collectors.base import SourceAdapter
from app.collectors.web.parsing import extract_description
from app.config import get_settings
from app.db.models import Listing, ListingExclusion, Search, SearchListing
from app.services.analytics.iqr import compute_price_stats
from app.services.regions import (
    exclude_regions_from_params,
    matches_region,
    regions_from_params,
)
from app.services.search_filter import (
    combined_text,
    desc_verdict_ok,
    exclude_keywords_from_params,
    first_matching_exclude,
    keywords_from_params,
    matches_keyword_groups,
)

logger = logging.getLogger(__name__)

WORD_SPLIT = re.compile(r"[^0-9a-zа-яё+]+")

CATEGORY_COPY = "copy"
CATEGORY_FAKE_BAIT = "fake_bait"
CATEGORY_IRRELEVANT = "irrelevant"
CATEGORY_DUPLICATE = "duplicate"
MODERATION_CATEGORIES = (
    CATEGORY_COPY,
    CATEGORY_FAKE_BAIT,
    CATEGORY_IRRELEVANT,
    CATEGORY_DUPLICATE,
)

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
    "не включается",
    "битый",
    "разбит",
    "восстановлен",
    "после ремонта",
    "на ремонт",
    "проблема с",
)
BAIT_WORDS = (
    "цена не",
    "предлогать цену",
    "предлагать цену",
    "приманка",
    "розыгрыш",
    "жеребьевк",
    "только сегодня",
)
CONTACT_WORDS = (
    "whatsapp",
    "ватсап",
    "вотсап",
    "telegram",
    "телеграм",
    "звоните",
    "пишите в",
)
SOFT_WORDS = ("торг", "срочно", "обмен", "дешево", "дешевле")


@dataclass(frozen=True, slots=True)
class Verdict:
    flagged: bool
    category: str | None
    reasons: list[str]
    score: float


@dataclass(frozen=True, slots=True)
class ModerationResult:
    total: int
    flagged: int
    ai_scored: int
    described: int
    median: float | None
    categories: dict[str, int] = field(default_factory=dict)
    desc_reviewed: int = 0
    ai_tokens_in: int = 0
    ai_tokens_out: int = 0
    ai_cost_usd: float = 0.0


def normalize_title(title: str) -> str:
    lowered = title.lower().replace("ё", "е")
    words = [word for word in WORD_SPLIT.split(lowered) if word]
    return " ".join(words)


def detect_clusters(
    rows: list[tuple[int, str, float | None, int | None]],
) -> dict[int, int]:
    """Кластеры «одинаковое название + одинаковая цена» от разных продавцов."""
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


def _contains_any(text: str, words: tuple[str, ...]) -> list[str]:
    return [word for word in words if word in text]


def evaluate_listing(
    title: str,
    description: str | None,
    price: float | None,
    median: float | None,
    cluster_size: int,
    *,
    low_price_ratio: float = 0.35,
    duplicate_min_cluster: int = 5,
) -> Verdict:
    """Детерминированные признаки с категорией: copy / irrelevant / fake_bait / duplicate."""
    title_text = title.lower().replace("ё", "е")
    description_text = (description or "").lower().replace("ё", "е")
    text = f"{title_text} {description_text}"
    reasons: list[str] = []
    score = 0.0
    category: str | None = None

    copy_hits = _contains_any(text, COPY_WORDS)
    if copy_hits:
        reasons.append("признаки копии/реплики: " + ", ".join(copy_hits))
        score = max(score, 0.9)
        category = category or CATEGORY_COPY

    junk_hits = _contains_any(text, JUNK_WORDS)
    if junk_hits:
        reasons.append("нерелевант/неисправность: " + ", ".join(junk_hits))
        score = max(score, 0.75)
        category = category or CATEGORY_IRRELEVANT

    bait_hits = _contains_any(text, BAIT_WORDS)
    if bait_hits:
        reasons.append("приманка в тексте: " + ", ".join(bait_hits))
        score = max(score, 0.7)
        category = category or CATEGORY_FAKE_BAIT

    if price is not None and median and median > 0 and price < median * low_price_ratio:
        reasons.append(f"цена ниже {int(low_price_ratio * 100)}% медианы")
        score = max(score, 0.6)
        category = category or CATEGORY_FAKE_BAIT

    if cluster_size >= duplicate_min_cluster:
        reasons.append(f"дубли: {cluster_size} объявлений с той же ценой")
        score = max(score, 0.55)
        category = category or CATEGORY_DUPLICATE

    contact_hits = _contains_any(text, CONTACT_WORDS)
    if contact_hits:
        reasons.append("контакты вне Авито: " + ", ".join(contact_hits))
        score = max(score, 0.45)

    soft = _contains_any(text, SOFT_WORDS)
    if soft:
        reasons.append("маркетинг: " + ", ".join(soft))

    flagged = score >= 0.5
    return Verdict(
        flagged=flagged,
        category=category if flagged else None,
        reasons=reasons,
        score=round(score, 3),
    )


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


async def enrich_descriptions(
    session: AsyncSession,
    transport: SourceAdapter,
    listings: list[tuple[int, str, str | None]],
    *,
    max_items: int,
    delay_min: float,
    delay_max: float,
) -> int:
    """Догружает описания для кандидатов (лимит и паузы, только новые)."""
    fetched = 0
    for index, (listing_id, url, existing) in enumerate(listings):
        if fetched >= max_items:
            break
        if existing or not url:
            continue
        try:
            page = await transport.fetch(url, expect_items=False)
            description = extract_description(page.body)
        except Exception as error:
            logger.warning("description fetch failed for %s: %s", listing_id, error)
            continue
        if description is None:
            logger.info("description not found on page for %s", listing_id)
            continue
        now = datetime.now(UTC)
        await session.execute(
            update(Listing)
            .where(Listing.id == listing_id)
            .values(description=description, description_fetched_at=now)
        )
        fetched += 1
        if index < len(listings) - 1:
            await asyncio.sleep(random.uniform(delay_min, max(delay_min, delay_max)))
    await session.flush()
    return fetched


def passes_base_filters(
    *,
    title: str,
    description: str | None,
    region: str | None,
    params: dict | None,
    manual_excluded: bool = False,
) -> bool:
    """Проходит ли объявление include/регион/ручные фильтры поиска (без стоп-слов).

    Модерация и AI работают только с релевантной выдачей: лишние модели не должны
    тратить токены и попадать в статистику.
    """
    if manual_excluded:
        return False
    groups = keywords_from_params(params)
    excludes = exclude_keywords_from_params(params)
    text = combined_text(title, description)
    if groups and not matches_keyword_groups(text, groups):
        return False
    if first_matching_exclude(title, excludes) is not None:
        return False
    return matches_region(region, regions_from_params(params), exclude_regions_from_params(params))


def _context_snippet(description: str, word: str, radius: int = 160) -> str:
    lowered = description.lower()
    index = lowered.find(word.lower())
    if index < 0:
        return description[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(description), index + len(word) + radius)
    return description[start:end].strip()


async def moderate_search(
    session: AsyncSession,
    search_id: Any,
    *,
    ai: bool | None = None,
    transport: SourceAdapter | None = None,
    with_descriptions: bool | None = None,
) -> ModerationResult:
    """Модерация активной выдачи поиска: правила, описания кандидатов, AI-скоринг."""
    settings = get_settings()
    if not settings.moderation_enabled:
        return ModerationResult(total=0, flagged=0, ai_scored=0, described=0, median=None)

    search = await session.get(Search, search_id)
    search_params = search.params if search is not None else None
    max_age_days = search_params.get("max_age_days") if isinstance(search_params, dict) else None
    statement = (
        select(
            Listing.id,
            Listing.title,
            Listing.current_price,
            Listing.seller_id,
            Listing.url,
            Listing.description,
            Listing.params,
            Listing.region,
        )
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .where(SearchListing.search_id == search_id, Listing.status == "active")
    )
    if isinstance(max_age_days, int) and not isinstance(max_age_days, bool) and max_age_days > 0:
        statement = statement.where(
            SearchListing.first_seen >= datetime.now(UTC) - timedelta(days=max_age_days)
        )
    rows = (await session.execute(statement)).all()
    listing_rows: list[
        tuple[
            int,
            str,
            float | None,
            int | None,
            str | None,
            str | None,
            dict | None,
            str | None,
        ]
    ] = [
        (
            row[0],
            row[1],
            float(row[2]) if row[2] is not None else None,
            row[3],
            row[4],
            row[5],
            row[6],
            row[7],
        )
        for row in rows
    ]
    manual_rows = await session.execute(
        select(ListingExclusion.listing_id).where(ListingExclusion.search_id == search_id)
    )
    manual_ids = {row[0] for row in manual_rows.all()}
    listing_rows = [
        row
        for row in listing_rows
        if passes_base_filters(
            title=row[1],
            description=row[5],
            region=row[7],
            params=search_params if isinstance(search_params, dict) else None,
            manual_excluded=row[0] in manual_ids,
        )
    ]
    prices = [row[2] for row in listing_rows if row[2] is not None]
    median = float(compute_price_stats(prices).median) if prices else None
    clusters = detect_clusters([(row[0], row[1], row[2], row[3]) for row in listing_rows])

    described = 0
    use_descriptions = (
        settings.moderation_descriptions_enabled if with_descriptions is None else with_descriptions
    )
    if use_descriptions and transport is not None and median is not None:
        scored_candidates: list[tuple[float, float, int, str, str | None]] = []
        for row in listing_rows:
            listing_id, title, price, _seller_id, url, description, _params, _region = row
            if description is not None:
                continue
            verdict = evaluate_listing(title, None, price, median, clusters.get(listing_id, 0))
            near_threshold = (
                price is not None and price < median * settings.moderation_ai_candidate_ratio
            )
            if verdict.flagged or near_threshold:
                price_ratio = price / median if price is not None and median else 1.0
                scored_candidates.append(
                    (verdict.score, price_ratio, listing_id, url or "", description)
                )
        scored_candidates.sort(key=lambda entry: (-entry[0], entry[1]))
        candidates: list[tuple[int, str, str | None]] = [
            (entry[2], entry[3], entry[4]) for entry in scored_candidates
        ]
        described = await enrich_descriptions(
            session,
            transport,
            candidates,
            max_items=settings.moderation_description_max_items,
            delay_min=settings.moderation_description_delay_min_seconds,
            delay_max=settings.moderation_description_delay_max_seconds,
        )
        refreshed = (
            await session.execute(
                select(Listing.id, Listing.description).where(
                    Listing.id.in_([row[0] for row in listing_rows])
                )
            )
        ).all()
        descriptions = {row[0]: row[1] for row in refreshed}
        listing_rows = [
            (
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                descriptions.get(row[0], row[5]),
                row[6],
                row[7],
            )
            for row in listing_rows
        ]

    now = datetime.now(UTC)
    use_ai = settings.moderation_ai_enabled if ai is None else ai
    ai_scored = 0
    ai_tokens_in = 0
    ai_tokens_out = 0
    ai_cost_usd = 0.0
    desc_ok_ids: set[tuple[int, str]] = set()
    desc_reviewed = 0
    if (
        use_ai
        and search is not None
        and settings.moderation_description_review_enabled
        and settings.deepseek_api_key
    ):
        groups = keywords_from_params(search.params)
        excludes = exclude_keywords_from_params(search.params)
        params_by_id = {row[0]: row[6] for row in listing_rows}
        review_candidates: list[tuple[int, str, str, str]] = []
        for (
            listing_id,
            title,
            _price,
            _seller,
            _url,
            description,
            listing_params,
            _region,
        ) in listing_rows:
            if not description:
                continue
            text = combined_text(title or "", description)
            word = first_matching_exclude(text, excludes)
            if word is None or first_matching_exclude(title or "", excludes) is not None:
                continue
            if groups and not matches_keyword_groups(text, groups):
                continue
            if desc_verdict_ok(listing_params, word):
                continue
            review_candidates.append(
                (listing_id, title or "", word, _context_snippet(description, word))
            )
        limited_review = review_candidates[: settings.moderation_description_review_max_items]
        for batch in _chunks(limited_review, settings.moderation_description_review_batch_size):
            try:
                review = await review_descriptions_batch(query=search.name, items=list(batch))
            except LlmNotConfiguredError:
                break
            except Exception as error:
                logger.warning("AI description review failed: %s", error)
                break
            await record_llm_run(
                session,
                task="description_context",
                result=review,
                prompt_version=DESCRIPTION_REVIEW_VERSION,
            )
            ai_tokens_in += review.tokens_in or 0
            ai_tokens_out += review.tokens_out or 0
            ai_cost_usd += review.cost_usd or 0.0
            decisions = {item.listing_id: item for item in review.content.items}
            for listing_id, _title, word, _snippet in batch:
                review_decision = decisions.get(listing_id)
                if review_decision is None:
                    continue
                stored = params_by_id.get(listing_id)
                new_params = dict(stored) if isinstance(stored, dict) else {}
                new_params["desc_verdict"] = {
                    "ok": not review_decision.actually_excluded,
                    "word": word,
                    "reason": review_decision.reason,
                    "at": now.isoformat(),
                }
                await session.execute(
                    update(Listing).where(Listing.id == listing_id).values(params=new_params)
                )
                if not review_decision.actually_excluded:
                    desc_ok_ids.add((listing_id, word))
                desc_reviewed += 1

    def _desc_pass(
        row: tuple[
            int,
            str,
            float | None,
            int | None,
            str | None,
            str | None,
            dict | None,
            str | None,
        ],
    ) -> bool:
        listing_id, title, _price, _seller, _url, description, row_params, _region = row
        word = first_matching_exclude(combined_text(title or "", description), excludes)
        if word is None:
            return True
        if first_matching_exclude(title or "", excludes) is not None:
            return False
        return (listing_id, word) in desc_ok_ids or desc_verdict_ok(
            row_params if isinstance(row_params, dict) else None, word
        )

    listing_rows = [row for row in listing_rows if _desc_pass(row)]
    prices = [row[2] for row in listing_rows if row[2] is not None]
    median = float(compute_price_stats(prices).median) if prices else None
    clusters = detect_clusters([(row[0], row[1], row[2], row[3]) for row in listing_rows])
    verdicts: dict[int, Verdict] = {}
    candidates_ai: list[tuple[int, str, float | None, str | None]] = []
    for listing_id, title, price, _seller_id, _url, description, _params, _region in listing_rows:
        verdict = evaluate_listing(
            title,
            description,
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
            candidates_ai.append((listing_id, title, price, description))

    for listing_id, verdict in verdicts.items():
        await session.execute(
            update(Listing)
            .where(Listing.id == listing_id)
            .values(
                is_flagged=verdict.flagged,
                flag_category=verdict.category,
                flag_reasons=verdict.reasons or None,
                relevance_score=verdict.score,
                moderated_at=now,
            )
        )

    if use_ai and candidates_ai and median is not None and settings.deepseek_api_key:
        limited = candidates_ai[: settings.moderation_max_ai_items]
        for batch in _chunks(limited, settings.moderation_ai_batch_size):
            try:
                result = await moderate_listings_batch(
                    query=search.name if search is not None else "",
                    median=median,
                    items=[(item[0], item[1], item[2], item[3]) for item in batch],
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
            ai_tokens_in += result.tokens_in or 0
            ai_tokens_out += result.tokens_out or 0
            ai_cost_usd += result.cost_usd or 0.0
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
                if decision.category in MODERATION_CATEGORIES:
                    category: str | None = decision.category
                else:
                    category = existing.category
                if flagged and category is None:
                    category = CATEGORY_FAKE_BAIT
                await session.execute(
                    update(Listing)
                    .where(Listing.id == decision.listing_id)
                    .values(
                        is_flagged=flagged,
                        flag_category=category if flagged else None,
                        flag_reasons=merged_reasons or None,
                        relevance_score=round(score, 3),
                        moderated_at=now,
                    )
                )
                verdicts[decision.listing_id] = Verdict(
                    flagged=flagged,
                    category=category if flagged else None,
                    reasons=merged_reasons,
                    score=round(score, 3),
                )

    await session.flush()
    categories: dict[str, int] = defaultdict(int)
    for verdict in verdicts.values():
        if verdict.flagged and verdict.category:
            categories[verdict.category] += 1
    return ModerationResult(
        total=len(listing_rows),
        flagged=sum(1 for verdict in verdicts.values() if verdict.flagged),
        ai_scored=ai_scored,
        described=described,
        median=median,
        categories=dict(categories),
        desc_reviewed=desc_reviewed,
        ai_tokens_in=ai_tokens_in,
        ai_tokens_out=ai_tokens_out,
        ai_cost_usd=round(ai_cost_usd, 6),
    )
