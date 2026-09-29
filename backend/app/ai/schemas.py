from typing import Literal

from pydantic import BaseModel, Field


class PriceActionRecommendation(BaseModel):
    recommended_price: float = Field(..., gt=0, description="Рекомендованная цена, руб.")
    pricing_strategy: Literal["undercut_p25", "match_median", "premium_p75", "keep_current"]
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    justification_points: list[str] = Field(..., min_length=1)
    risk_assessment: str


class MarketDigest(BaseModel):
    headline: str
    demand_signal: Literal["weak", "balanced", "strong"]
    price_range_comment: str
    competitor_notes: list[str]
    recommended_actions: list[str]
