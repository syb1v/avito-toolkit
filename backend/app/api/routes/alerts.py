import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select

from app.api.deps import DbSession
from app.db.models import Alert, Search
from app.services.alerts import evaluate_search_alerts

router = APIRouter(tags=["alerts"])

MAX_ALERTS = 200


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    payload: dict | None
    status: str
    created_at: datetime


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(
    session: DbSession,
    status: str | None = None,
    search_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[Alert]:
    query = select(Alert).order_by(Alert.created_at.desc()).limit(max(1, min(limit, MAX_ALERTS)))
    if status:
        query = query.where(Alert.status == status)
    if search_id is not None:
        query = query.where(Alert.payload["search_id"].astext == str(search_id))
    rows = await session.execute(query)
    return list(rows.scalars().all())


class AlertClearRequest(BaseModel):
    search_id: uuid.UUID | None = None
    status: str | None = None


@router.post("/alerts/clear")
async def clear_alerts(payload: AlertClearRequest, session: DbSession) -> dict[str, int]:
    """Удаляет алерты по фильтру: search_id и/или status. Без фильтров — все."""
    statement = delete(Alert)
    if payload.status:
        statement = statement.where(Alert.status == payload.status)
    if payload.search_id is not None:
        statement = statement.where(Alert.payload["search_id"].astext == str(payload.search_id))
    result = await session.execute(statement)
    await session.commit()
    return {"deleted": int(getattr(result, "rowcount", 0) or 0)}


@router.delete("/alerts/{alert_id}", status_code=204)
async def delete_alert(alert_id: uuid.UUID, session: DbSession) -> None:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    await session.delete(alert)
    await session.commit()


@router.post("/alerts/{alert_id}/ack", response_model=AlertOut)
async def ack_alert(alert_id: uuid.UUID, session: DbSession) -> Alert:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    alert.status = "acked"
    await session.commit()
    await session.refresh(alert)
    return alert


@router.post("/searches/{search_id}/alerts/evaluate", response_model=list[AlertOut])
async def evaluate_alerts(search_id: uuid.UUID, session: DbSession) -> list[Alert]:
    search = await session.get(Search, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="search not found")
    created = await evaluate_search_alerts(session, search_id)
    await session.commit()
    for alert in created:
        await session.refresh(alert)
    return created
