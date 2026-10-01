import uuid
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import DbSession
from app.api.schemas import PositionOut, PriceStatsOut
from app.db.models import OurListing, Search
from app.services.matching import (
    build_our_position,
    build_overview,
    list_matches,
    match_all_our_listings,
    match_our_listing,
    update_match_status,
)
from app.services.our_listings import (
    import_from_search,
    normalize_import_rows,
    upsert_our_listings,
)
from app.services.recommendations import build_recommendations

router = APIRouter(tags=["matching"])


class OurListingCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1)
    price: float = Field(gt=0)
    cost_price: float | None = Field(default=None, gt=0)
    category: str | None = None
    params: dict = Field(default_factory=dict)


class OurListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku: str
    title: str
    price: float
    cost_price: float | None
    category: str | None
    is_active: bool


class MatchOut(BaseModel):
    listing_id: int
    title: str
    price: float | None
    url: str | None
    status: str
    similarity_score: float


class MatchStatusUpdate(BaseModel):
    status: Literal["auto_matched", "confirmed", "rejected"]


class OverviewOut(BaseModel):
    sku: str
    title: str
    our_price: float
    cost_price: float | None
    is_active: bool
    avito_status: str | None
    avito_url: str | None
    matched_count: int
    market_median: float | None
    market_p25: float | None
    market_p75: float | None
    delta_to_median_pct: float | None
    cheaper_share: float | None


class RecommendationOut(BaseModel):
    sku: str
    title: str
    our_price: float
    cost_price: float | None
    market_median: float | None
    matched_count: int
    strategy: str
    target_price: float
    clamped_price: float
    delta_pct: float
    requires_approval: bool


class ImportRequest(BaseModel):
    items: list[dict[str, object]] = Field(min_length=1, max_length=5000)


class ImportOut(BaseModel):
    created: int
    updated: int
    skipped: int


@router.get("/our-listings", response_model=list[OurListingOut])
async def list_our_listings(session: DbSession) -> list[OurListing]:
    rows = await session.execute(select(OurListing).order_by(OurListing.sku))
    return list(rows.scalars().all())


@router.post("/our-listings", response_model=OurListingOut, status_code=201)
async def upsert_our_listing(payload: OurListingCreate, session: DbSession) -> OurListing:
    our = await session.get(OurListing, payload.sku)
    if our is None:
        our = OurListing(**payload.model_dump())
        session.add(our)
    else:
        for key, value in payload.model_dump().items():
            setattr(our, key, value)
    await session.commit()
    await session.refresh(our)
    return our


@router.get("/our-listings/overview", response_model=list[OverviewOut])
async def our_listings_overview(session: DbSession) -> list[OverviewOut]:
    rows = await build_overview(session)
    return [OverviewOut(**asdict(row)) for row in rows]


@router.get("/our-listings/recommendations", response_model=list[RecommendationOut])
async def our_listings_recommendations(session: DbSession) -> list[RecommendationOut]:
    recommendations = await build_recommendations(session)
    return [RecommendationOut(**asdict(item)) for item in recommendations]


@router.post("/our-listings/match-all")
async def match_all(session: DbSession) -> dict[str, int]:
    matched = await match_all_our_listings(session)
    return {"matched": matched}


@router.post("/our-listings/import", response_model=ImportOut)
async def import_our_listings(payload: ImportRequest, session: DbSession) -> ImportOut:
    rows, invalid = normalize_import_rows(payload.items)
    result = await upsert_our_listings(session, rows)
    return ImportOut(
        created=result.created,
        updated=result.updated,
        skipped=result.skipped + invalid,
    )


@router.post("/our-listings/import-from-search/{search_id}", response_model=ImportOut)
async def import_our_listings_from_search(search_id: uuid.UUID, session: DbSession) -> ImportOut:
    if await session.get(Search, search_id) is None:
        raise HTTPException(status_code=404, detail="search not found")
    result = await import_from_search(session, search_id)
    return ImportOut(created=result.created, updated=result.updated, skipped=result.skipped)


@router.post("/our-listings/{sku}/match", response_model=list[MatchOut])
async def run_match(sku: str, session: DbSession) -> list[MatchOut]:
    try:
        await match_our_listing(session, sku)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    matches = await list_matches(session, sku)
    return [MatchOut(**asdict(match)) for match in matches]


@router.get("/our-listings/{sku}/matches", response_model=list[MatchOut])
async def get_matches(sku: str, session: DbSession) -> list[MatchOut]:
    matches = await list_matches(session, sku)
    return [MatchOut(**asdict(match)) for match in matches]


@router.patch("/our-listings/{sku}/matches/{listing_id}", response_model=MatchStatusUpdate)
async def patch_match_status(
    sku: str, listing_id: int, payload: MatchStatusUpdate, session: DbSession
) -> MatchStatusUpdate:
    try:
        updated = await update_match_status(session, sku, listing_id, payload.status)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not updated:
        raise HTTPException(status_code=404, detail="match not found")
    return payload


@router.get("/our-listings/{sku}/position", response_model=PositionOut)
async def get_position(sku: str, session: DbSession) -> PositionOut:
    try:
        position = await build_our_position(session, sku)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if position is None:
        raise HTTPException(status_code=404, detail="no matches with prices yet")
    stats = position.stats
    return PositionOut(
        our_price=position.our_price,
        matched_count=position.matched_count,
        cheaper_share=position.cheaper_share,
        delta_to_median_pct=position.delta_to_median_pct,
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
