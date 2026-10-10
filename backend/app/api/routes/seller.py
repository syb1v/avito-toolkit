"""Фаза 6: правки своих объявлений (dry-run/live) и журнал."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession
from app.config import get_settings
from app.db.models import ListingEdit, OurListing
from app.services.ownership import require_seller
from app.services.recommendations import build_recommendations

router = APIRouter(prefix="/our-listings/edits", tags=["seller"])

OPEN_STATUSES = ("draft", "approved", "applying", "reverting")
MAX_BATCH = 50
DEFAULT_BATCH = 10


class EditOut(BaseModel):
    id: uuid.UUID
    sku: str
    title: str | None = None
    old_price: float
    target_price: float
    delta_pct: float
    strategy: str
    status: str
    mode: str
    error: str | None = None
    screenshot_path: str | None = None
    ai_summary: str | None = None
    created_at: datetime
    applied_at: datetime | None = None
    reverted_at: datetime | None = None


class EditsListOut(BaseModel):
    mode: str
    live_edits: bool
    items: list[EditOut]


class CreateEditsIn(BaseModel):
    sku: str | None = None
    max_items: int = Field(default=DEFAULT_BATCH, ge=1, le=MAX_BATCH)


class CreateEditsOut(BaseModel):
    created: int
    items: list[EditOut]


class ManualEditIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    price: float = Field(gt=0, le=100_000_000)


class ManualEditOut(BaseModel):
    edit: EditOut
    applied: bool
    requires_approval: bool


async def _overview_map(session: DbSession) -> dict[str, str]:
    rows = await session.execute(select(OurListing.sku, OurListing.title))
    return {row[0]: row[1] for row in rows.all()}


def _row(edit: ListingEdit, title: str | None) -> EditOut:
    return EditOut(
        id=edit.id,
        sku=edit.sku,
        title=title,
        old_price=float(edit.old_price),
        target_price=float(edit.target_price),
        delta_pct=float(edit.delta_pct),
        strategy=edit.strategy,
        status=edit.status,
        mode=edit.mode,
        error=edit.error,
        screenshot_path=edit.screenshot_path,
        ai_summary=edit.ai_summary,
        created_at=edit.created_at,
        applied_at=edit.applied_at,
        reverted_at=edit.reverted_at,
    )


@router.get("", response_model=EditsListOut)
async def list_edits(session: DbSession, limit: int = 50, sku: str | None = None) -> EditsListOut:
    settings = get_settings()
    statement = select(ListingEdit)
    if sku:
        statement = statement.where(ListingEdit.sku == sku)
    rows = (
        (
            await session.execute(
                statement.order_by(ListingEdit.created_at.desc()).limit(max(1, min(limit, 200)))
            )
        )
        .scalars()
        .all()
    )
    titles = await _overview_map(session)
    return EditsListOut(
        mode=settings.seller_edit_mode,
        live_edits=settings.seller_edit_mode == "live",
        items=[_row(edit, titles.get(edit.sku)) for edit in rows],
    )


@router.post("", response_model=CreateEditsOut, status_code=201)
async def create_edits(payload: CreateEditsIn, session: DbSession) -> CreateEditsOut:
    """Создаёт черновики правок по детерминированным рекомендациям (HITL по порогу)."""
    settings = get_settings()
    recommendations = await build_recommendations(session)
    if payload.sku:
        recommendations = [item for item in recommendations if item.sku == payload.sku]

    open_rows = await session.execute(
        select(ListingEdit.sku).where(ListingEdit.status.in_(OPEN_STATUSES))
    )
    busy_skus = {row[0] for row in open_rows.all()}

    created: list[ListingEdit] = []
    for recommendation in recommendations:
        if len(created) >= payload.max_items:
            break
        if recommendation.sku in busy_skus:
            continue
        our = await session.get(OurListing, recommendation.sku)
        if our is None or our.account_id is None:
            continue
        edit = ListingEdit(
            sku=recommendation.sku,
            account_id=our.account_id,
            old_price=recommendation.our_price,
            target_price=recommendation.clamped_price,
            delta_pct=recommendation.delta_pct,
            strategy=recommendation.strategy,
            status="draft" if recommendation.requires_approval else "approved",
            mode=settings.seller_edit_mode,
        )
        session.add(edit)
        created.append(edit)
    await session.commit()
    titles = await _overview_map(session)
    for edit in created:
        await session.refresh(edit)
    return CreateEditsOut(
        created=len(created), items=[_row(edit, titles.get(edit.sku)) for edit in created]
    )


@router.post("/manual", response_model=ManualEditOut, status_code=201)
async def create_manual_edit(payload: ManualEditIn, session: DbSession) -> ManualEditOut:
    """Ручная цена: создаёт правку и сразу ставит её в очередь применения."""
    settings = get_settings()
    our = await session.get(OurListing, payload.sku)
    if our is None:
        raise HTTPException(status_code=404, detail=f"our listing {payload.sku} not found")
    await require_seller(session, our)
    open_rows = await session.execute(
        select(ListingEdit.id).where(
            ListingEdit.sku == payload.sku, ListingEdit.status.in_(OPEN_STATUSES)
        )
    )
    if open_rows.first() is not None:
        raise HTTPException(
            status_code=409, detail="по этому SKU уже есть открытая правка — закройте её"
        )
    old_price = float(our.price)
    target = float(payload.price)
    delta_pct = 0.0 if old_price <= 0 else (target - old_price) / old_price * 100
    requires_approval = abs(delta_pct) > settings.reprice_hitl_threshold_pct
    edit = ListingEdit(
        sku=payload.sku,
        account_id=our.account_id,
        old_price=old_price,
        target_price=target,
        delta_pct=delta_pct,
        strategy="manual",
        status="draft" if requires_approval else "approved",
        mode=settings.seller_edit_mode,
    )
    session.add(edit)
    await session.commit()
    await session.refresh(edit)
    if edit.status == "approved":
        _enqueue(edit.id, revert=False)
    titles = await _overview_map(session)
    return ManualEditOut(
        edit=_row(edit, titles.get(edit.sku)),
        applied=edit.status == "approved",
        requires_approval=requires_approval,
    )


async def _load(session: DbSession, edit_id: uuid.UUID) -> ListingEdit:
    edit = await session.get(ListingEdit, edit_id)
    if edit is None:
        raise HTTPException(status_code=404, detail="edit not found")
    return edit


@router.post("/{edit_id}/approve", response_model=EditOut)
async def approve_edit(edit_id: uuid.UUID, session: DbSession) -> EditOut:
    edit = await _load(session, edit_id)
    if edit.status != "draft":
        raise HTTPException(status_code=409, detail=f"нельзя одобрить из статуса {edit.status}")
    edit.status = "approved"
    await session.commit()
    await session.refresh(edit)
    return _row(edit, (await _overview_map(session)).get(edit.sku))


@router.post("/{edit_id}/reject", response_model=EditOut)
async def reject_edit(edit_id: uuid.UUID, session: DbSession) -> EditOut:
    edit = await _load(session, edit_id)
    if edit.status not in ("draft", "approved"):
        raise HTTPException(status_code=409, detail=f"нельзя отклонить из статуса {edit.status}")
    edit.status = "rejected"
    await session.commit()
    await session.refresh(edit)
    return _row(edit, (await _overview_map(session)).get(edit.sku))


def _enqueue(edit_id: uuid.UUID, revert: bool) -> None:
    from app.workers.tasks import apply_listing_edit

    apply_listing_edit.send(str(edit_id), revert)


@router.post("/{edit_id}/apply", response_model=EditOut, status_code=202)
async def apply_edit(edit_id: uuid.UUID, session: DbSession) -> EditOut:
    edit = await _load(session, edit_id)
    if edit.status != "approved":
        raise HTTPException(
            status_code=409, detail=f"сначала одобрите правку (статус {edit.status})"
        )
    edit.status = "applying"
    edit.error = None
    await session.commit()
    _enqueue(edit.id, revert=False)
    await session.refresh(edit)
    return _row(edit, (await _overview_map(session)).get(edit.sku))


@router.post("/{edit_id}/revert", response_model=EditOut, status_code=202)
async def revert_edit(edit_id: uuid.UUID, session: DbSession) -> EditOut:
    edit = await _load(session, edit_id)
    if edit.status not in ("applied", "dry_run"):
        raise HTTPException(status_code=409, detail=f"нечего откатывать (статус {edit.status})")
    edit.status = "reverting"
    await session.commit()
    _enqueue(edit.id, revert=True)
    await session.refresh(edit)
    return _row(edit, (await _overview_map(session)).get(edit.sku))
