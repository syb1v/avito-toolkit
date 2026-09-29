from app.ai.client import complete_structured
from app.ai.prompts import (
    PRICE_ADVISOR_SYSTEM_PROMPT,
    PRICE_ADVISOR_VERSION,
    build_price_prompt,
)
from app.ai.schemas import PriceActionRecommendation
from app.services.pricing import RepricingContext


async def advise_price(
    *,
    title: str,
    current_price: float,
    cost_price: float | None,
    context: RepricingContext,
) -> PriceActionRecommendation:
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
