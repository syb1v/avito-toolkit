from typing import Literal

from pydantic import BaseModel, Field


class PriceActionRecommendation(BaseModel):
    recommended_price: float = Field(..., gt=0, description="Рекомендованная цена, руб.")
    pricing_strategy: Literal["undercut_p25", "match_median", "premium_p75", "keep_current"]
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    justification_points: list[str] = Field(..., min_length=1)
    risk_assessment: str


class PriceSuggestion(BaseModel):
    sku: str = Field(..., description="SKU нашего товара из блока «Наши товары»")
    target_price: float = Field(..., gt=0, description="Рекомендованная наша цена, руб.")
    reason: str = Field(..., description="Короткое обоснование по рынку")


class MarketDigest(BaseModel):
    headline: str
    demand_signal: Literal["weak", "balanced", "strong"]
    price_range_comment: str
    competitor_notes: list[str]
    recommended_actions: list[str]
    price_suggestions: list[PriceSuggestion] = Field(default_factory=list)


class RepriceSummaryItem(BaseModel):
    sku: str
    reason: str = Field(..., description="1–2 предложения: почему меняем цену")


class RepriceSummary(BaseModel):
    headline: str
    items: list[RepriceSummaryItem]


class ChatPlan(BaseModel):
    tools: list[str] = Field(default_factory=list)
    search: str | None = None
    action_type: Literal["crawl", "digest", "clear_alerts", "manual_edit"] | None = None
    action_search: str | None = None
    action_sku: str | None = None
    action_price: float | None = None


class ChatAnswer(BaseModel):
    answer: str


class SearchFilterItem(BaseModel):
    avito_id: int | None = None
    query: str = Field(..., description="поисковая строка Авито, 2–5 слов, без цветов")
    keyword_groups: list[list[str]] = Field(
        ..., description="AND-группы: бренд, модель; внутри группы — варианты написания"
    )
    exclude_keywords: list[str] = Field(
        ..., description="другие цвета/модели/мусор: копия, ремонт, запчасти и т.п."
    )


class SearchFiltersBatch(BaseModel):
    items: list[SearchFilterItem]


class DescriptionReviewItem(BaseModel):
    listing_id: int
    actually_excluded: bool = Field(
        ..., description="True — стоп-слово по делу, объявление реально не подходит"
    )
    reason: str


class DescriptionReviewBatch(BaseModel):
    items: list[DescriptionReviewItem]


class ModerationItem(BaseModel):
    listing_id: int
    relevant: bool
    likely_fake_or_copy: bool
    category: Literal["copy", "fake_bait", "irrelevant", "duplicate", "none"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str


class ModerationBatch(BaseModel):
    items: list[ModerationItem]
