import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession
from app.config import get_settings
from app.db.models import Alert, Listing, LlmRun, OurListing, Search
from app.services.alerts import search_alive_clause
from app.services.progress import list_running_progress
from app.services.queues import system_health

router = APIRouter(tags=["dashboard"])

LATEST_ALERTS_LIMIT = 5


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


class AiTaskSpendOut(BaseModel):
    task: str
    runs: int
    cost_usd: float


class AiSpendOut(BaseModel):
    day_usd: float
    month_usd: float
    total_usd: float
    by_task: list[AiTaskSpendOut]


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
    ai_spend: AiSpendOut


async def _count(session: AsyncSession, model: type, *conditions: ColumnElement[bool]) -> int:
    statement = select(func.count()).select_from(model)
    for condition in conditions:
        statement = statement.where(condition)
    return int(await session.scalar(statement) or 0)


async def _ai_spend(session: AsyncSession) -> AiSpendOut:
    now = datetime.now(UTC)
    day_ago = now - timedelta(days=1)
    month_ago = now - timedelta(days=30)

    async def _sum_since(moment: datetime | None) -> float:
        statement = select(func.coalesce(func.sum(LlmRun.cost_usd), 0))
        if moment is not None:
            statement = statement.where(LlmRun.created_at >= moment)
        value = await session.scalar(statement)
        return float(value) if value is not None else 0.0

    rows = await session.execute(
        select(
            LlmRun.task,
            func.count(),
            func.coalesce(func.sum(LlmRun.cost_usd), 0),
        )
        .where(LlmRun.created_at >= month_ago)
        .group_by(LlmRun.task)
        .order_by(func.coalesce(func.sum(LlmRun.cost_usd), 0).desc())
    )
    return AiSpendOut(
        day_usd=round(await _sum_since(day_ago), 6),
        month_usd=round(await _sum_since(month_ago), 6),
        total_usd=round(await _sum_since(None), 6),
        by_task=[
            AiTaskSpendOut(task=row[0], runs=int(row[1]), cost_usd=round(float(row[2] or 0), 6))
            for row in rows.all()
        ],
    )


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
        health = await system_health(redis, window_seconds=settings.worker_alive_window_seconds)
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
        worker_alive=bool(health["worker_alive"]),
        queues=QueueStatusOut(
            crawl=int(health["crawl_queue"]),
            analytics=int(health["analytics_queue"]),
        ),
        active_crawls=active_crawls,
        latest_alerts=latest,
        ai_spend=await _ai_spend(session),
    )
