import uuid
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession
from app.api.schemas import PriceStatsOut
from app.db.models import Search
from app.services.analytics.service import build_search_summary, fetch_daily_history

router = APIRouter(prefix="/searches", tags=["analytics"])

MAX_HISTORY_DAYS = 365


class MarketSummaryOut(BaseModel):
    search_id: uuid.UUID
    name: str
    url: str
    is_active: bool
    active_count: int
    new_today_count: int
    delisted_today_count: int
    delisted_7d: int
    delisting_velocity: float
    avg_lifetime_days: float | None
    flagged_count: int
    flag_categories: dict[str, int]
    stats: PriceStatsOut | None


class DailyPointOut(BaseModel):
    calc_date: date
    active_count: int
    new_today_count: int
    delisted_today_count: int
    price_min: float | None
    price_max: float | None
    price_median: float | None
    price_p25: float | None
    price_p75: float | None
    avg_lifetime_days: float | None


async def _load_search(session: AsyncSession, search_id: uuid.UUID) -> Search:
    search = await session.get(Search, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="search not found")
    return search


@router.get("/{search_id}/summary", response_model=MarketSummaryOut)
async def get_summary(search_id: uuid.UUID, session: DbSession) -> MarketSummaryOut:
    search = await _load_search(session, search_id)
    summary = await build_search_summary(session, search_id)
    stats = summary.stats
    return MarketSummaryOut(
        search_id=search_id,
        name=search.name,
        url=search.url,
        is_active=search.is_active,
        active_count=summary.active_count,
        new_today_count=summary.new_today_count,
        delisted_today_count=summary.delisted_today_count,
        delisted_7d=summary.delisted_7d,
        delisting_velocity=summary.delisting_velocity,
        avg_lifetime_days=summary.avg_lifetime_days,
        flagged_count=summary.flagged_count,
        flag_categories=summary.flag_categories,
        stats=(
            PriceStatsOut(
                count=stats.count,
                price_min=stats.price_min,
                price_max=stats.price_max,
                mean=stats.mean,
                median=stats.median,
                p25=stats.p25,
                p75=stats.p75,
            )
            if stats is not None
            else None
        ),
    )


@router.get("/{search_id}/history", response_model=list[DailyPointOut])
async def get_history(
    search_id: uuid.UUID, session: DbSession, days: int = 30
) -> list[DailyPointOut]:
    await _load_search(session, search_id)
    rows = await fetch_daily_history(session, search_id, max(1, min(days, MAX_HISTORY_DAYS)))
    return [
        DailyPointOut(
            calc_date=row.calc_date,
            active_count=row.active_count,
            new_today_count=row.new_today_count,
            delisted_today_count=row.delisted_today_count,
            price_min=row.price_min,
            price_max=row.price_max,
            price_median=row.price_median,
            price_p25=row.price_p25,
            price_p75=row.price_p75,
            avg_lifetime_days=row.avg_lifetime_days,
        )
        for row in rows
    ]
