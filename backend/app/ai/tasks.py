from collections.abc import Sequence

from app.ai.client import LlmResult, complete_structured
from app.ai.prompts import (
    DIGEST_SYSTEM_PROMPT,
    DIGEST_VERSION,
    PRICE_ADVISOR_SYSTEM_PROMPT,
    PRICE_ADVISOR_VERSION,
    build_digest_prompt,
    build_price_prompt,
)
from app.ai.schemas import MarketDigest, PriceActionRecommendation
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
        ),
        task="market_digest",
        prompt_version=DIGEST_VERSION,
    )
