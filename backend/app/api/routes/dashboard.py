from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession
from app.db.models import Alert, Listing, OurListing, Search

router = APIRouter(tags=["dashboard"])

LATEST_ALERTS_LIMIT = 5


class DashboardAlertOut(BaseModel):
    id: str
    type: str
    payload: dict | None
    created_at: datetime


class DashboardOut(BaseModel):
    searches_total: int
    searches_active: int
    listings_active: int
    our_listings_active: int
    alerts_new: int
    latest_alerts: list[DashboardAlertOut]


async def _count(session: AsyncSession, model: type, *conditions: ColumnElement[bool]) -> int:
    statement = select(func.count()).select_from(model)
    for condition in conditions:
        statement = statement.where(condition)
    return int(await session.scalar(statement) or 0)


@router.get("/dashboard", response_model=DashboardOut)
async def get_dashboard(session: DbSession) -> DashboardOut:
    alerts_rows = await session.execute(
        select(Alert)
        .where(Alert.status == "new")
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
        alerts_new=await _count(session, Alert, Alert.status == "new"),
        latest_alerts=latest,
    )
