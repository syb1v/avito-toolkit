from pydantic import BaseModel


class PriceStatsOut(BaseModel):
    count: int
    price_min: float
    price_max: float
    mean: float
    median: float
    p25: float
    p75: float


class PositionOut(BaseModel):
    our_price: float
    matched_count: int
    cheaper_share: float | None
    delta_to_median_pct: float | None
    stats: PriceStatsOut | None
