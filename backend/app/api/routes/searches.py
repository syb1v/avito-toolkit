import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.config import get_settings
from app.db.models import Listing, Search, SearchListing
from app.services.progress import progress_key, read_progress
from app.services.searches import import_searches, normalize_search_rows

router = APIRouter(prefix="/searches", tags=["searches"])


class SearchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1)
    params: dict = Field(default_factory=dict)
    schedule_cron: str = "*/30 * * * *"
    priority: int = 100


class SearchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url: str
    params: dict | None
    schedule_cron: str
    priority: int
    is_active: bool


class ListingRead(BaseModel):
    id: int
    title: str
    price: float | None
    url: str | None
    status: str
    last_position: int | None


@router.get("", response_model=list[SearchRead])
async def list_searches(session: DbSession) -> list[Search]:
    result = await session.execute(select(Search).order_by(Search.priority, Search.name))
    return list(result.scalars().all())


@router.post("", response_model=SearchRead, status_code=201)
async def create_search(payload: SearchCreate, session: DbSession) -> Search:
    search = Search(**payload.model_dump())
    session.add(search)
    await session.commit()
    await session.refresh(search)
    return search


class SearchImportRequest(BaseModel):
    items: list[dict[str, object]] = Field(min_length=1, max_length=1000)


class SearchImportOut(BaseModel):
    created: int
    updated: int
    skipped: int


@router.post("/import", response_model=SearchImportOut)
async def import_searches_endpoint(
    payload: SearchImportRequest, session: DbSession
) -> SearchImportOut:
    rows, invalid = normalize_search_rows(payload.items)
    result = await import_searches(session, rows)
    return SearchImportOut(
        created=result.created,
        updated=result.updated,
        skipped=result.skipped + invalid,
    )


@router.post("/{search_id}/crawl", status_code=202)
async def trigger_crawl(search_id: uuid.UUID, session: DbSession) -> dict[str, str]:
    search = await session.get(Search, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="search not found")
    from app.workers.tasks import crawl_search

    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        await redis.delete(progress_key(search_id))
    finally:
        await redis.aclose()
    message = crawl_search.send(str(search_id))
    return {"status": "queued", "message_id": message.message_id}


class ProgressOut(BaseModel):
    search_id: uuid.UUID
    status: str
    stage: str | None = None
    page: int | None = None
    max_pages: int | None = None
    listings_seen: int | None = None
    result: dict | None = None
    error: str | None = None
    updated_at: str | None = None
    last_crawl_at: datetime | None = None


@router.get("/{search_id}/progress", response_model=ProgressOut)
async def get_search_progress(search_id: uuid.UUID, session: DbSession) -> ProgressOut:
    if await session.get(Search, search_id) is None:
        raise HTTPException(status_code=404, detail="search not found")

    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        data = await read_progress(redis, search_id)
    finally:
        await redis.aclose()

    last_crawl_at = await session.scalar(
        select(func.max(SearchListing.last_seen)).where(SearchListing.search_id == search_id)
    )
    if not data:
        return ProgressOut(search_id=search_id, status="idle", last_crawl_at=last_crawl_at)
    return ProgressOut(
        search_id=search_id,
        status=str(data.get("status") or "idle"),
        stage=str(data["stage"]) if data.get("stage") else None,
        page=int(data["page"]) if data.get("page") is not None else None,
        max_pages=int(data["max_pages"]) if data.get("max_pages") is not None else None,
        listings_seen=(
            int(data["listings_seen"]) if data.get("listings_seen") is not None else None
        ),
        result=data.get("result") if isinstance(data.get("result"), dict) else None,
        error=str(data["error"]) if data.get("error") else None,
        updated_at=str(data["updated_at"]) if data.get("updated_at") else None,
        last_crawl_at=last_crawl_at,
    )


@router.get("/{search_id}/listings", response_model=list[ListingRead])
async def list_search_listings(
    search_id: uuid.UUID, session: DbSession, limit: int = 100
) -> list[ListingRead]:
    rows = await session.execute(
        select(
            Listing.id,
            Listing.title,
            Listing.current_price,
            Listing.url,
            Listing.status,
            SearchListing.last_position,
        )
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .where(SearchListing.search_id == search_id)
        .order_by(SearchListing.last_position.nulls_last())
        .limit(max(1, min(limit, 500)))
    )
    return [
        ListingRead(
            id=row[0],
            title=row[1],
            price=float(row[2]) if row[2] is not None else None,
            url=row[3],
            status=row[4],
            last_position=row[5],
        )
        for row in rows.all()
    ]
