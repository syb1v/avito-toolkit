import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import DbSession
from app.db.models import Listing, Search, SearchListing

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


@router.post("/{search_id}/crawl", status_code=202)
async def trigger_crawl(search_id: uuid.UUID, session: DbSession) -> dict[str, str]:
    search = await session.get(Search, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="search not found")
    from app.workers.tasks import crawl_search

    message = crawl_search.send(str(search_id))
    return {"status": "queued", "message_id": message.message_id}


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
