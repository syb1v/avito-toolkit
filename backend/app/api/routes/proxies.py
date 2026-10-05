import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select

from app.api.deps import DbSession
from app.config import get_settings
from app.db.models import Proxy
from app.services.proxy_pool import (
    ProxyParseError,
    build_proxy_pool,
    parse_proxy_entry,
)

router = APIRouter(tags=["proxies"])

EMPTY_STATUS: dict[str, Any] = {
    "enabled": False,
    "configured": False,
    "mode": None,
    "count": 0,
    "alive": 0,
    "in_cooldown": 0,
    "antibot_blocked": 0,
    "entries": [],
}


class ProxyCreate(BaseModel):
    url: str = Field(min_length=5, max_length=500)
    note: str | None = None


class ProxyUpdate(BaseModel):
    enabled: bool | None = None
    note: str | None = None


def _entry_row(row: Proxy, status_by_label: dict[str, dict[str, Any]]) -> dict[str, Any]:
    try:
        label = parse_proxy_entry(row.url).label
        scheme = parse_proxy_entry(row.url).scheme
    except ProxyParseError:
        label, scheme = row.url, "http"
    state = status_by_label.get(label, {})
    return {
        "id": str(row.id),
        "label": label,
        "scheme": scheme,
        "enabled": row.enabled,
        "note": row.note,
        "healthy": state.get("healthy") if row.enabled else None,
        "failures": state.get("failures", 0),
        "cooldown_seconds_left": state.get("cooldown_seconds_left", 0),
        "antibot_blocked": state.get("antibot_blocked", False),
        "antibot_seconds_left": state.get("antibot_seconds_left", 0),
        "last_ok": state.get("last_ok"),
        "last_error": state.get("last_error"),
        "latency_ms": state.get("latency_ms"),
        "exit_ip": state.get("exit_ip"),
    }


@router.get("/proxies")
async def get_proxies(session: DbSession) -> dict:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        pool = await build_proxy_pool(redis, session, force=True)
        status = await pool.status() if pool is not None else dict(EMPTY_STATUS)
    finally:
        await redis.aclose()
    rows = (await session.execute(select(Proxy).order_by(Proxy.created_at))).scalars().all()
    status_by_label = {entry["label"]: entry for entry in status.get("entries", [])}
    entries = [_entry_row(row, status_by_label) for row in rows]
    return {
        "enabled": settings.proxy_enabled,
        "configured": bool(entries),
        "mode": status.get("mode") or settings.proxy_rotation,
        "count": len(entries),
        "alive": sum(1 for entry in entries if entry["enabled"] and entry["healthy"]),
        "in_cooldown": sum(
            1 for entry in entries if entry["enabled"] and entry["cooldown_seconds_left"] > 0
        ),
        "antibot_blocked": sum(
            1 for entry in entries if entry["enabled"] and entry["antibot_blocked"]
        ),
        "entries": entries,
    }


@router.post("/proxies", status_code=201)
async def create_proxy(payload: ProxyCreate, session: DbSession) -> dict[str, Any]:
    try:
        entry = parse_proxy_entry(payload.url)
    except ProxyParseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    exists = await session.scalar(select(Proxy.id).where(Proxy.url == entry.url))
    if exists is not None:
        raise HTTPException(status_code=409, detail="такой прокси уже добавлен")
    proxy = Proxy(url=entry.url, note=payload.note, enabled=True)
    session.add(proxy)
    await session.commit()
    await session.refresh(proxy)
    return _entry_row(proxy, {})


@router.patch("/proxies/{proxy_id}")
async def update_proxy(
    proxy_id: uuid.UUID, payload: ProxyUpdate, session: DbSession
) -> dict[str, Any]:
    proxy = await session.get(Proxy, proxy_id)
    if proxy is None:
        raise HTTPException(status_code=404, detail="proxy not found")
    if payload.enabled is not None:
        proxy.enabled = payload.enabled
    if payload.note is not None:
        proxy.note = payload.note
    await session.commit()
    await session.refresh(proxy)
    return _entry_row(proxy, {})


@router.delete("/proxies/{proxy_id}", status_code=204)
async def delete_proxy(proxy_id: uuid.UUID, session: DbSession) -> None:
    proxy = await session.get(Proxy, proxy_id)
    if proxy is None:
        raise HTTPException(status_code=404, detail="proxy not found")
    await session.delete(proxy)
    await session.commit()


@router.post("/proxies/check")
async def check_proxies_now(session: DbSession, avito: bool = True) -> dict:
    """Healthcheck пула. ``avito=true`` — дополнительно проверить, пускает ли Авито."""
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        pool = await build_proxy_pool(redis, session, force=True)
        if pool is None:
            return {"checked": 0, "ok": 0, "failed": 0, "avito_checked": False}
        return await pool.check_all(avito=avito)
    finally:
        await redis.aclose()
