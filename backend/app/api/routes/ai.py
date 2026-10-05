import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.ai.client import LlmNotConfiguredError
from app.ai.prompts import DIGEST_VERSION, PRICE_ADVISOR_VERSION
from app.ai.runs import record_llm_run
from app.ai.tasks import advise_price, generate_market_digest
from app.api.deps import DbSession
from app.api.schemas import PositionOut, PriceStatsOut
from app.config import Settings, get_settings
from app.db.models import AiDigest, Listing, LlmRun, OurListing, Search, SearchListing
from app.services.analytics.service import build_search_summary, fetch_daily_history
from app.services.matching import build_our_position
from app.services.pricing import RepricingContext, build_price_target

router = APIRouter(tags=["ai"])

TOP_LISTINGS_FOR_PROMPT = 10
HISTORY_FOR_PROMPT = 14
MAX_LLM_RUNS = 100


class DigestOut(BaseModel):
    search_id: uuid.UUID
    headline: str
    demand_signal: str
    price_range_comment: str
    competitor_notes: list[str]
    recommended_actions: list[str]
    model: str
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None
    created_at: datetime | None = None


class PriceActionOut(BaseModel):
    recommended_price: float
    pricing_strategy: str
    confidence_score: float
    justification_points: list[str]
    risk_assessment: str


class AdviceOut(BaseModel):
    sku: str
    our_price: float
    strategy: str
    target_price: float
    clamped_price: float
    delta_pct: float
    requires_approval: bool
    llm_configured: bool
    ai: PriceActionOut | None
    position: PositionOut


class LlmRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task: str
    model: str
    prompt_version: str
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None
    created_at: datetime


def _llm_configured(settings: Settings) -> bool:
    if settings.llm_model.startswith("deepseek/"):
        return bool(settings.deepseek_api_key)
    return True


@router.post("/searches/{search_id}/digest", response_model=DigestOut)
async def create_digest(search_id: uuid.UUID, session: DbSession) -> DigestOut:
    search = await session.get(Search, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="search not found")

    summary = await build_search_summary(session, search_id)
    top_rows = await session.execute(
        select(Listing.title, Listing.current_price)
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .where(SearchListing.search_id == search_id, Listing.status == "active")
        .order_by(SearchListing.last_position.nulls_last())
        .limit(TOP_LISTINGS_FOR_PROMPT)
    )
    top_listings = [
        (row[0], float(row[1]) if row[1] is not None else None) for row in top_rows.all()
    ]
    history_rows = await fetch_daily_history(session, search_id, HISTORY_FOR_PROMPT)
    history = [
        (
            str(row.calc_date),
            float(row.price_median) if row.price_median is not None else None,
        )
        for row in history_rows
    ]
    stats = summary.stats

    try:
        result = await generate_market_digest(
            search_name=search.name,
            active_count=summary.active_count,
            new_today=summary.new_today_count,
            delisted_today=summary.delisted_today_count,
            delisted_7d=summary.delisted_7d,
            delisting_velocity=summary.delisting_velocity,
            median=stats.median if stats else None,
            p25=stats.p25 if stats else None,
            p75=stats.p75 if stats else None,
            top_listings=top_listings,
            history=history,
        )
    except LlmNotConfiguredError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    await record_llm_run(
        session, task="market_digest", result=result, prompt_version=DIGEST_VERSION
    )
    digest = result.content
    out = DigestOut(
        search_id=search_id,
        headline=digest.headline,
        demand_signal=digest.demand_signal,
        price_range_comment=digest.price_range_comment,
        competitor_notes=digest.competitor_notes,
        recommended_actions=digest.recommended_actions,
        model=result.model,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        cost_usd=result.cost_usd,
    )
    stored = AiDigest(
        search_id=search_id,
        payload=out.model_dump(mode="json", exclude={"search_id", "created_at"}),
        model=result.model,
    )
    session.add(stored)
    await session.commit()
    await session.refresh(stored)
    out.created_at = stored.created_at
    return out


@router.get("/searches/{search_id}/digest", response_model=DigestOut)
async def get_latest_digest(search_id: uuid.UUID, session: DbSession) -> DigestOut:
    """Последний сохранённый дайджест — виден всем без повторной генерации."""
    row = await session.scalar(
        select(AiDigest)
        .where(AiDigest.search_id == search_id)
        .order_by(AiDigest.created_at.desc())
        .limit(1)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="digest not generated yet")
    payload = dict(row.payload or {})
    return DigestOut(
        search_id=search_id,
        headline=str(payload.get("headline", "")),
        demand_signal=str(payload.get("demand_signal", "")),
        price_range_comment=str(payload.get("price_range_comment", "")),
        competitor_notes=list(payload.get("competitor_notes") or []),
        recommended_actions=list(payload.get("recommended_actions") or []),
        model=str(payload.get("model") or row.model),
        tokens_in=payload.get("tokens_in"),
        tokens_out=payload.get("tokens_out"),
        cost_usd=payload.get("cost_usd"),
        created_at=row.created_at,
    )


@router.post("/our-listings/{sku}/advice", response_model=AdviceOut)
async def create_advice(
    sku: str, session: DbSession, search_id: uuid.UUID | None = None
) -> AdviceOut:
    our = await session.get(OurListing, sku)
    if our is None:
        raise HTTPException(status_code=404, detail=f"our listing {sku} not found")
    position = await build_our_position(session, sku)
    if position is None or position.stats is None:
        raise HTTPException(status_code=404, detail="no matches with prices yet")

    settings = get_settings()
    delisted_7d = 0
    active_total = position.matched_count
    if search_id is not None:
        market = await build_search_summary(session, search_id)
        delisted_7d = market.delisted_7d
        active_total = market.active_count or position.matched_count

    context = RepricingContext(
        median=position.stats.median,
        p25=position.stats.p25,
        p75=position.stats.p75,
        active_competitors=position.matched_count,
        delisted_7d=delisted_7d,
        active_total=active_total,
    )
    target = build_price_target(
        context,
        float(our.price),
        min_price=float(our.cost_price) if our.cost_price is not None else None,
        max_step_pct=settings.reprice_max_step_pct,
        hitl_threshold_pct=settings.reprice_hitl_threshold_pct,
    )

    llm_configured = _llm_configured(settings)
    ai: PriceActionOut | None = None
    if llm_configured:
        try:
            llm_result = await advise_price(
                title=our.title,
                current_price=float(our.price),
                cost_price=float(our.cost_price) if our.cost_price is not None else None,
                context=context,
            )
        except LlmNotConfiguredError:
            llm_configured = False
        else:
            await record_llm_run(
                session,
                task="price_advice",
                result=llm_result,
                prompt_version=PRICE_ADVISOR_VERSION,
            )
            await session.commit()
            recommendation = llm_result.content
            ai = PriceActionOut(
                recommended_price=recommendation.recommended_price,
                pricing_strategy=recommendation.pricing_strategy,
                confidence_score=recommendation.confidence_score,
                justification_points=recommendation.justification_points,
                risk_assessment=recommendation.risk_assessment,
            )

    return AdviceOut(
        sku=sku,
        our_price=float(our.price),
        strategy=target.strategy.value,
        target_price=target.target_price,
        clamped_price=target.clamped_price,
        delta_pct=target.delta_pct,
        requires_approval=target.requires_approval,
        llm_configured=llm_configured,
        ai=ai,
        position=PositionOut(
            our_price=position.our_price,
            matched_count=position.matched_count,
            cheaper_share=position.cheaper_share,
            delta_to_median_pct=position.delta_to_median_pct,
            stats=(
                None
                if position.stats is None
                else PriceStatsOut(
                    count=position.stats.count,
                    price_min=position.stats.price_min,
                    price_max=position.stats.price_max,
                    mean=position.stats.mean,
                    median=position.stats.median,
                    p25=position.stats.p25,
                    p75=position.stats.p75,
                )
            ),
        ),
    )


@router.get("/llm-runs", response_model=list[LlmRunOut])
async def list_llm_runs(session: DbSession, limit: int = 20) -> list[LlmRun]:
    rows = await session.execute(
        select(LlmRun).order_by(LlmRun.created_at.desc()).limit(max(1, min(limit, MAX_LLM_RUNS)))
    )
    return list(rows.scalars().all())
