from collections.abc import Sequence

from app.ai.client import LlmResult, complete_structured
from app.ai.prompts import (
    DESCRIPTION_REVIEW_SYSTEM_PROMPT,
    DESCRIPTION_REVIEW_VERSION,
    DIGEST_SYSTEM_PROMPT,
    DIGEST_VERSION,
    MODERATION_SYSTEM_PROMPT,
    MODERATION_VERSION,
    PRICE_ADVISOR_SYSTEM_PROMPT,
    PRICE_ADVISOR_VERSION,
    REPRICE_SUMMARY_SYSTEM_PROMPT,
    REPRICE_SUMMARY_VERSION,
    SEARCH_FILTERS_SYSTEM_PROMPT,
    SEARCH_FILTERS_VERSION,
    build_description_review_prompt,
    build_digest_prompt,
    build_moderation_prompt,
    build_price_prompt,
    build_reprice_summary_prompt,
    build_search_filters_prompt,
)
from app.ai.schemas import (
    DescriptionReviewBatch,
    MarketDigest,
    ModerationBatch,
    PriceActionRecommendation,
    RepriceSummary,
    SearchFiltersBatch,
)
from app.services.pricing import RepricingContext


async def advise_price(
    *,
    title: str,
    current_price: float,
    cost_price: float | None,
    context: RepricingContext,
) -> LlmResult[PriceActionRecommendation]:
    return await complete_structured(
        PriceActionRecommendation,
        system_prompt=PRICE_ADVISOR_SYSTEM_PROMPT,
        user_prompt=build_price_prompt(
            title=title,
            current_price=current_price,
            cost_price=cost_price,
            context=context,
        ),
        task="price_advice",
        prompt_version=PRICE_ADVISOR_VERSION,
    )


async def generate_market_digest(
    *,
    search_name: str,
    active_count: int,
    new_today: int,
    delisted_today: int,
    delisted_7d: int,
    delisting_velocity: float,
    median: float | None,
    p25: float | None,
    p75: float | None,
    top_listings: Sequence[tuple[str, float | None]],
    history: Sequence[tuple[str, float | None]] = (),
    our_listings: Sequence[tuple[str, str, float | None]] = (),
) -> LlmResult[MarketDigest]:
    return await complete_structured(
        MarketDigest,
        system_prompt=DIGEST_SYSTEM_PROMPT,
        user_prompt=build_digest_prompt(
            search_name=search_name,
            active_count=active_count,
            new_today=new_today,
            delisted_today=delisted_today,
            delisted_7d=delisted_7d,
            delisting_velocity=delisting_velocity,
            median=median,
            p25=p25,
            p75=p75,
            top_listings=top_listings,
            history=history,
            our_listings=our_listings,
        ),
        task="market_digest",
        prompt_version=DIGEST_VERSION,
    )


async def review_descriptions_batch(
    *,
    query: str,
    items: list[tuple[int, str, str, str]],
) -> LlmResult[DescriptionReviewBatch]:
    return await complete_structured(
        DescriptionReviewBatch,
        system_prompt=DESCRIPTION_REVIEW_SYSTEM_PROMPT,
        user_prompt=build_description_review_prompt(query=query, items=items),
        task="description_context",
        prompt_version=DESCRIPTION_REVIEW_VERSION,
    )


async def moderate_listings_batch(
    *,
    query: str,
    median: float | None,
    items: list[tuple[int, str, float | None, str | None]],
) -> LlmResult[ModerationBatch]:
    return await complete_structured(
        ModerationBatch,
        system_prompt=MODERATION_SYSTEM_PROMPT,
        user_prompt=build_moderation_prompt(query=query, median=median, items=items),
        task="listing_moderation",
        prompt_version=MODERATION_VERSION,
    )


async def summarize_price_edits(
    *,
    items: list[tuple[str, str, float, float, str, float | None, float | None, float | None, int]],
) -> LlmResult[RepriceSummary]:
    return await complete_structured(
        RepriceSummary,
        system_prompt=REPRICE_SUMMARY_SYSTEM_PROMPT,
        user_prompt=build_reprice_summary_prompt(items=items),
        task="reprice_summary",
        prompt_version=REPRICE_SUMMARY_VERSION,
    )


async def generate_search_filters(
    *,
    items: list[tuple[int | None, str, str | None]],
) -> LlmResult[SearchFiltersBatch]:
    return await complete_structured(
        SearchFiltersBatch,
        system_prompt=SEARCH_FILTERS_SYSTEM_PROMPT,
        user_prompt=build_search_filters_prompt(items=items),
        task="search_filters",
        prompt_version=SEARCH_FILTERS_VERSION,
        max_tokens=2000,
    )
