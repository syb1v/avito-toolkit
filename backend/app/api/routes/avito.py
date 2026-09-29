from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession
from app.config import get_settings
from app.db.models import Search
from app.integrations.avito_api.client import (
    AvitoApiClient,
    AvitoApiError,
    AvitoApiNotConfiguredError,
)
from app.services.alerts import evaluate_search_alerts
from app.services.avito_sync import DEFAULT_MAX_PAGES, sync_our_listings
from app.services.matching import match_all_our_listings

router = APIRouter(prefix="/avito", tags=["avito"])


class AvitoStatusOut(BaseModel):
    configured: bool
    base_url: str
    user_id: int | None


class SyncRequest(BaseModel):
    max_pages: int = Field(default=DEFAULT_MAX_PAGES, ge=1, le=100)
    match: bool = True
    status: str = "active"


class SyncOut(BaseModel):
    created: int
    updated: int
    skipped: int
    pages_fetched: int
    matched: int
    alerts_created: int


@router.get("/status", response_model=AvitoStatusOut)
async def get_status() -> AvitoStatusOut:
    settings = get_settings()
    return AvitoStatusOut(
        configured=bool(settings.avito_client_id and settings.avito_client_secret),
        base_url=settings.avito_base_url,
        user_id=settings.avito_user_id,
    )


@router.post("/sync", response_model=SyncOut)
async def sync(payload: SyncRequest, session: DbSession) -> SyncOut:
    """Выгрузка своих объявлений через официальный API + матчинг + алерты."""
    try:
        client = AvitoApiClient.from_settings()
    except AvitoApiNotConfiguredError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    try:
        result = await sync_our_listings(
            session, client, max_pages=payload.max_pages, status=payload.status
        )
    except AvitoApiError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        await client.close()

    matched = 0
    alerts_created = 0
    if payload.match:
        matched = await match_all_our_listings(session)
        search_rows = await session.execute(select(Search.id).where(Search.is_active.is_(True)))
        for (search_id,) in search_rows.all():
            alerts_created += len(await evaluate_search_alerts(session, search_id))
        await session.commit()

    return SyncOut(
        created=result.created,
        updated=result.updated,
        skipped=result.skipped,
        pages_fetched=result.pages_fetched,
        matched=matched,
        alerts_created=alerts_created,
    )
