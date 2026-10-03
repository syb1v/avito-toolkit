import time
import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession
from app.config import get_settings
from app.db.models import Alert, Listing, OurListing, Search
from app.services.alerts import search_alive_clause
from app.services.progress import list_running_progress

router = APIRouter(tags=["dashboard"])

LATEST_ALERTS_LIMIT = 5
CRAWL_QUEUE = "dramatiq:crawl"
ANALYTICS_QUEUE = "dramatiq:analytics"
HEARTBEAT_KEY = "dramatiq:__heartbeats__"
WORKER_ALIVE_WINDOW_SECONDS = 90


class DashboardAlertOut(BaseModel):
    id: str
    type: str
    payload: dict | None
    created_at: datetime


class QueueStatusOut(BaseModel):
    crawl: int
    analytics: int


class ActiveCrawlOut(BaseModel):
    search_id: str
    search_name: str | None
    stage: str | None
    page: int | None
    max_pages: int | None
    listings_seen: int | None
    started_at: str | None


class DashboardOut(BaseModel):
    searches_total: int
    searches_active: int
    listings_active: int
    our_listings_active: int
    alerts_new: int
    worker_alive: bool
    queues: QueueStatusOut
    active_crawls: list[ActiveCrawlOut]
    latest_alerts: list[DashboardAlertOut]


async def _count(session: AsyncSession, model: type, *conditions: ColumnElement[bool]) -> int:
    statement = select(func.count()).select_from(model)
    for condition in conditions:
        statement = statement.where(condition)
    return int(await session.scalar(statement) or 0)


async def _worker_alive(redis: Redis) -> bool:
    try:
        rows = await redis.zrange(HEARTBEAT_KEY, -1, -1, withscores=True)
    except Exception:
        return False
    if not rows:
        return False
    try:
        score = float(rows[0][1])
    except (TypeError, ValueError):
        return False
    return (time.time() - score) < WORKER_ALIVE_WINDOW_SECONDS


async def _active_crawls(session: AsyncSession, redis: Redis) -> list[ActiveCrawlOut]:
    running = await list_running_progress(redis)
    if not running:
        return []
    ids: list[uuid.UUID] = []
    for item in running:
        try:
            ids.append(uuid.UUID(str(item.get("search_id"))))
        except (TypeError, ValueError):
            continue
    names: dict[str, str] = {}
    if ids:
        rows = await session.execute(select(Search.id, Search.name).where(Search.id.in_(ids)))
        names = {str(row[0]): row[1] for row in rows.all()}
    return [
        ActiveCrawlOut(
            search_id=str(item.get("search_id")),
            search_name=item.get("search_name") or names.get(str(item.get("search_id"))),
            stage=str(item["stage"]) if item.get("stage") else None,
            page=int(item["page"]) if item.get("page") is not None else None,
            max_pages=(int(item["max_pages"]) if item.get("max_pages") is not None else None),
            listings_seen=(
                int(item["listings_seen"]) if item.get("listings_seen") is not None else None
            ),
            started_at=str(item["started_at"]) if item.get("started_at") else None,
        )
        for item in running
    ]


@router.get("/dashboard", response_model=DashboardOut)
async def get_dashboard(session: DbSession) -> DashboardOut:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        crawl_queue = int(await redis.llen(CRAWL_QUEUE) or 0)
        analytics_queue = int(await redis.llen(ANALYTICS_QUEUE) or 0)
        worker_alive = await _worker_alive(redis)
        active_crawls = await _active_crawls(session, redis)
    finally:
        await redis.aclose()

    alerts_rows = await session.execute(
        select(Alert)
        .where(Alert.status == "new", search_alive_clause())
        .order_by(Alert.created_at.desc())
        .limit(LATEST_ALERTS_LIMIT)
    )
    latest = [
        DashboardAlertOut(
            id=str(alert.id),
            type=alert.type,
            payload=alert.payload,
            created_at=alert.created_at,
        )
        for alert in alerts_rows.scalars().all()
    ]
    return DashboardOut(
        searches_total=await _count(session, Search),
        searches_active=await _count(session, Search, Search.is_active.is_(True)),
        listings_active=await _count(session, Listing, Listing.status == "active"),
        our_listings_active=await _count(session, OurListing, OurListing.is_active.is_(True)),
        alerts_new=await _count(session, Alert, Alert.status == "new", search_alive_clause()),
        worker_alive=worker_alive,
        queues=QueueStatusOut(crawl=crawl_queue, analytics=analytics_queue),
        active_crawls=active_crawls,
        latest_alerts=latest,
    )
