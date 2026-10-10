from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from rapidfuzz import fuzz, process
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Listing, OurListing, ProductMarketMatch, Search, SearchListing
from app.services.analytics.iqr import PriceStats, compute_price_stats
from app.services.search_filter import normalize_text

MATCH_STATUSES = ("auto_matched", "confirmed", "rejected")

# Слова-модификаторы модели: если у одной стороны есть, а у другой нет — это другой товар.
MODEL_MODIFIERS = {"pro", "plus", "max", "mini", "ultra", "se"}
CAPACITY_UNITS = {"gb": "гб", "гб": "гб", "tb": "тб", "тб": "тб"}
# Known model-family anchors. They are deliberately treated as identity fields,
# not fuzzy title vocabulary: shared editions (for example Opera de Paris) must
# never make two different families comparable.
MODEL_FAMILY_TOKENS = {
    "gemini",
    "mania",
    "phantom",
    "dione",
    "lyra",
    "twin",
    "eleven",
    "a9",
    "a1",
    "homepod",
    "airpods",
    "watch",
    "iphone",
    "ipad",
    "macbook",
}


@dataclass(frozen=True, slots=True)
class ProductIdentity:
    brand: str | None
    model_family: str | None
    numeric_markers: frozenset[str]
    edition: str | None
    capacities: frozenset[str]
    modifiers: frozenset[str]


def parse_product_identity(value: str) -> ProductIdentity:
    tokens = _tokens(value)
    families = _model_family(tokens)
    brand = tokens[0] if tokens else None
    edition = (
        "opera de paris"
        if "opera" in tokens and "de" in tokens and "paris" in tokens
        else None
    )
    return ProductIdentity(
        brand=brand,
        model_family=next(iter(families), None),
        numeric_markers=frozenset(_numbers(tokens) - _capacity_numbers(tokens)),
        edition=edition,
        capacities=frozenset(_capacities(tokens)),
        modifiers=frozenset(set(tokens) & MODEL_MODIFIERS),
    )


def identity_conflicts(left: ProductIdentity, right: ProductIdentity) -> list[str]:
    conflicts: list[str] = []
    if left.brand and right.brand and left.brand != right.brand:
        conflicts.append("brand")
    if left.model_family and right.model_family and left.model_family != right.model_family:
        conflicts.append("model_family")
    if (
        left.numeric_markers
        and right.numeric_markers
        and left.numeric_markers.isdisjoint(right.numeric_markers)
    ):
        conflicts.append("generation")
    if left.capacities and right.capacities and left.capacities != right.capacities:
        conflicts.append("capacity")
    if left.modifiers != right.modifiers:
        conflicts.append("variant")
    return conflicts


def _identity_payload(identity: ProductIdentity) -> dict[str, object]:
    return {
        "brand": identity.brand,
        "model_family": identity.model_family,
        "numeric_markers": sorted(identity.numeric_markers),
        "edition": identity.edition,
        "capacities": sorted(identity.capacities),
        "modifiers": sorted(identity.modifiers),
    }


def _tokens(value: str) -> list[str]:
    return normalize_text(value).split()


def _capacities(tokens: Sequence[str]) -> set[str]:
    """Ёмкости вида «256 гб» → {256гб}; единицы приводятся к гб/тб."""
    result: set[str] = set()
    for index, token in enumerate(tokens):
        unit = CAPACITY_UNITS.get(token)
        if unit is not None and index > 0 and tokens[index - 1].isdigit():
            result.add(f"{tokens[index - 1]}{unit}")
    return result


def _numbers(tokens: Sequence[str]) -> set[str]:
    return {token for token in tokens if token.isdigit()}


def _capacity_numbers(tokens: Sequence[str]) -> set[str]:
    return {
        tokens[index - 1]
        for index, token in enumerate(tokens)
        if token in CAPACITY_UNITS and index > 0 and tokens[index - 1].isdigit()
    }


def _model_family(tokens: Sequence[str]) -> set[str]:
    return {token for token in tokens if token in MODEL_FAMILY_TOKENS}


def _variant_compatible(query_tokens: Sequence[str], candidate_tokens: Sequence[str]) -> bool:
    """Отсекает чужие модели: Pro/Plus/Max, ёмкости и серии не должны расходиться."""
    query_set = set(query_tokens)
    candidate_set = set(candidate_tokens)
    query_identity = parse_product_identity(" ".join(query_tokens))
    candidate_identity = parse_product_identity(" ".join(candidate_tokens))
    if "model_family" in identity_conflicts(query_identity, candidate_identity):
        return False
    if (query_set & MODEL_MODIFIERS) != (candidate_set & MODEL_MODIFIERS):
        return False
    query_caps = _capacities(query_tokens)
    candidate_caps = _capacities(candidate_tokens)
    if query_caps and candidate_caps and query_caps != candidate_caps:
        return False
    query_numbers = _numbers(query_tokens) - _capacity_numbers(query_tokens)
    candidate_numbers = _numbers(candidate_tokens) - _capacity_numbers(candidate_tokens)
    return not (query_numbers and candidate_numbers and not (query_numbers & candidate_numbers))


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    listing_id: int
    title: str
    price: float | None


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate: MatchCandidate
    score: float


@dataclass(frozen=True, slots=True)
class MatchView:
    listing_id: int
    title: str
    price: float | None
    url: str | None
    status: str
    similarity_score: float


@dataclass(frozen=True, slots=True)
class MarketPosition:
    our_price: float
    matched_count: int
    stats: PriceStats | None
    cheaper_share: float | None
    delta_to_median_pct: float | None


@dataclass(frozen=True, slots=True)
class OverviewRow:
    sku: str
    title: str
    our_price: float
    cost_price: float | None
    account: str | None
    is_active: bool
    avito_status: str | None
    avito_url: str | None
    matched_count: int
    market_median: float | None
    market_p25: float | None
    market_p75: float | None
    delta_to_median_pct: float | None
    cheaper_share: float | None


def rank_candidates(
    query: str,
    candidates: Sequence[MatchCandidate],
    min_score: float = 75.0,
    limit: int = 10,
) -> list[RankedCandidate]:
    """Нечёткий матчинг заголовков через rapidfuzz (token_set_ratio).

    Перед скорингом отсекаются варианты чужих моделей: Pro/Plus/Max/Mini/Ultra,
    другая ёмкость (256 ГБ vs 512 ГБ) или другой номер серии.
    """
    query_tokens = _tokens(query)
    compatible = [
        candidate
        for candidate in candidates
        if _variant_compatible(query_tokens, _tokens(candidate.title))
    ]
    choices = {candidate.listing_id: candidate.title for candidate in compatible}
    if not choices:
        return []
    results = process.extract(
        query,
        choices,
        scorer=fuzz.token_set_ratio,
        limit=limit,
        score_cutoff=min_score,
    )
    by_id = {candidate.listing_id: candidate for candidate in compatible}
    return [RankedCandidate(by_id[listing_id], float(score)) for _, score, listing_id in results]


def compute_market_position(
    our_price: float, prices: Sequence[float], use_iqr: bool = True
) -> MarketPosition:
    if not prices:
        return MarketPosition(our_price, 0, None, None, None)
    stats = compute_price_stats(prices, use_iqr=use_iqr)
    cheaper = sum(1 for price in prices if price < our_price)
    return MarketPosition(
        our_price=our_price,
        matched_count=len(prices),
        stats=stats,
        cheaper_share=cheaper / len(prices),
        delta_to_median_pct=(our_price - stats.median) / stats.median * 100,
    )


async def match_our_listing(session: AsyncSession, sku: str) -> list[RankedCandidate]:
    """Подбирает конкурентов для нашего SKU и сохраняет матчи."""
    our = await session.get(OurListing, sku)
    if our is None:
        raise LookupError(f"our listing {sku} not found")
    settings = get_settings()
    active_listing_ids = (
        select(SearchListing.listing_id)
        .join(Search, Search.id == SearchListing.search_id)
        .where(Search.is_active.is_(True))
    )
    rows = await session.execute(
        select(Listing.id, Listing.title, Listing.current_price)
        .where(
            Listing.status == "active",
            Listing.current_price.is_not(None),
            Listing.id.in_(active_listing_ids),
        )
        .order_by(Listing.last_seen.desc())
        .limit(settings.match_max_candidates)
    )
    candidates = [
        MatchCandidate(row[0], row[1], float(row[2]) if row[2] is not None else None)
        for row in rows.all()
    ]
    ranked = rank_candidates(
        our.title,
        candidates,
        min_score=float(settings.match_min_score),
        limit=settings.match_top_n,
    )
    ranked_ids = [item.candidate.listing_id for item in ranked]
    if ranked:
        now = datetime.now(UTC)
        query_identity = parse_product_identity(our.title)
        statement = pg_insert(ProductMarketMatch).values(
            [
                {
                    "our_sku_id": sku,
                    "market_listing_id": ranked_item.candidate.listing_id,
                    "similarity_score": ranked_item.score,
                    "match_status": "auto_matched",
                    "identity": {
                        "query": _identity_payload(query_identity),
                        "candidate": _identity_payload(
                            parse_product_identity(ranked_item.candidate.title)
                        ),
                    },
                    "conflict_reasons": [],
                    "matched_at": now,
                }
                for ranked_item in ranked
            ]
        )
        statement = statement.on_conflict_do_update(
            index_elements=[
                ProductMarketMatch.our_sku_id,
                ProductMarketMatch.market_listing_id,
            ],
                    set_={
                        "similarity_score": statement.excluded.similarity_score,
                        "identity": statement.excluded.identity,
                        "conflict_reasons": statement.excluded.conflict_reasons,
                        "matched_at": statement.excluded.matched_at,
            },
            where=ProductMarketMatch.match_status == "auto_matched",
        )
        await session.execute(statement)
    # Убираем устаревшие авто-матчи: лоты из удалённых поисков и чужие модели.
    # Подтверждённые/отклонённые оператором матчи не трогаем.
    prune = delete(ProductMarketMatch).where(
        ProductMarketMatch.our_sku_id == sku,
        ProductMarketMatch.match_status == "auto_matched",
    )
    if ranked_ids:
        prune = prune.where(ProductMarketMatch.market_listing_id.not_in(ranked_ids))
    await session.execute(prune)
    await session.commit()
    return ranked


async def list_matches(session: AsyncSession, sku: str) -> list[MatchView]:
    rows = await session.execute(
        select(ProductMarketMatch, Listing)
        .join(Listing, Listing.id == ProductMarketMatch.market_listing_id)
        .where(ProductMarketMatch.our_sku_id == sku)
        .order_by(ProductMarketMatch.similarity_score.desc())
    )
    views: list[MatchView] = []
    for match, listing in rows.all():
        views.append(
            MatchView(
                listing_id=listing.id,
                title=listing.title,
                price=float(listing.current_price) if listing.current_price is not None else None,
                url=listing.url,
                status=match.match_status,
                similarity_score=match.similarity_score,
            )
        )
    return views


async def update_match_status(
    session: AsyncSession, sku: str, listing_id: int, status: str
) -> bool:
    if status not in MATCH_STATUSES:
        raise ValueError(f"unknown match status: {status}")
    match = await session.get(ProductMarketMatch, (sku, listing_id))
    if match is None:
        return False
    match.match_status = status
    await session.commit()
    return True


async def build_our_position(session: AsyncSession, sku: str) -> MarketPosition | None:
    our = await session.get(OurListing, sku)
    if our is None:
        raise LookupError(f"our listing {sku} not found")
    rows = await session.execute(
        select(Listing.current_price)
        .join(ProductMarketMatch, ProductMarketMatch.market_listing_id == Listing.id)
        .where(
            ProductMarketMatch.our_sku_id == sku,
            ProductMarketMatch.match_status != "rejected",
            Listing.current_price.is_not(None),
        )
    )
    prices = [float(row[0]) for row in rows.all() if row[0] is not None]
    if not prices:
        return None
    return compute_market_position(float(our.price), prices)


async def match_all_our_listings(session: AsyncSession) -> int:
    """Прогоняет матчинг по всем активным нашим SKU."""
    rows = await session.execute(
        select(OurListing.sku).where(OurListing.is_active.is_(True)).order_by(OurListing.sku)
    )
    matched = 0
    for (sku,) in rows.all():
        await match_our_listing(session, sku)
        matched += 1
    return matched


async def build_overview(session: AsyncSession) -> list[OverviewRow]:
    """Сводка по нашим SKU: цена, статус на Авито, матчи и дельта к медиане."""
    our_rows = (await session.execute(select(OurListing).order_by(OurListing.sku))).scalars().all()
    price_rows = await session.execute(
        select(ProductMarketMatch.our_sku_id, Listing.current_price)
        .join(Listing, Listing.id == ProductMarketMatch.market_listing_id)
        .where(
            ProductMarketMatch.match_status != "rejected",
            Listing.current_price.is_not(None),
        )
    )
    grouped: dict[str, list[float]] = {}
    for sku, price in price_rows.all():
        if price is not None:
            grouped.setdefault(sku, []).append(float(price))

    overview: list[OverviewRow] = []
    for our in our_rows:
        prices = grouped.get(our.sku, [])
        position = compute_market_position(float(our.price), prices) if prices else None
        stats = position.stats if position is not None else None
        overview.append(
            OverviewRow(
                sku=our.sku,
                title=our.title,
                our_price=float(our.price),
                cost_price=float(our.cost_price) if our.cost_price is not None else None,
                account=our.account,
                is_active=our.is_active,
                avito_status=our.avito_status,
                avito_url=our.avito_url,
                matched_count=position.matched_count if position is not None else 0,
                market_median=stats.median if stats is not None else None,
                market_p25=stats.p25 if stats is not None else None,
                market_p75=stats.p75 if stats is not None else None,
                delta_to_median_pct=(
                    position.delta_to_median_pct if position is not None else None
                ),
                cheaper_share=position.cheaper_share if position is not None else None,
            )
        )
    return overview
