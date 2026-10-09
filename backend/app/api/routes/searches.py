import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import DbSession
from app.config import get_settings
from app.db.models import Alert, Listing, ListingExclusion, Search, SearchListing, Seller
from app.services.progress import CrawlProgress, read_progress
from app.services.regions import (
    exclude_regions_from_params,
    matches_region,
    normalize_region,
    regions_from_params,
)
from app.services.search_filter import (
    combined_text,
    exclude_keywords_from_params,
    first_matching_exclude,
    first_missing_group,
    keywords_from_params,
    matches_exclude_keywords,
    matches_keyword_groups,
)
from app.services.searches import import_searches, merge_params, normalize_search_rows
from app.services.seller_filter import (
    EXCLUDE_KEY,
    TARGET_KEY,
    ref_matches_seller,
    seller_filter_reason,
    seller_refs_from_params,
)

router = APIRouter(prefix="/searches", tags=["searches"])


class SearchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1)
    params: dict = Field(default_factory=dict)
    schedule_cron: str = "*/30 * * * *"
    priority: int = 100
    account_id: uuid.UUID | None = None


class SearchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = Field(default=None, min_length=1)
    params: dict | None = None
    schedule_cron: str | None = None
    priority: int | None = None
    is_active: bool | None = None
    account_id: uuid.UUID | None = None


class SearchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url: str
    params: dict | None
    schedule_cron: str
    priority: int
    is_active: bool
    account_id: uuid.UUID | None = None


class ListingRead(BaseModel):
    id: int
    title: str
    price: float | None
    url: str | None
    status: str
    last_position: int | None
    is_flagged: bool = False
    flag_category: str | None = None
    flag_reasons: list[str] | None = None
    relevance_score: float | None = None
    description_snippet: str | None = None
    region: str | None = None
    manual_excluded: bool = False
    seller_name: str | None = None
    seller_url: str | None = None
    exclude_reason: str | None = None
    exclude_detail: str | None = None
    excluded: bool = False
    first_seen: datetime | None = None


@router.get("", response_model=list[SearchRead])
async def list_searches(session: DbSession) -> list[Search]:
    result = await session.execute(select(Search).order_by(Search.priority, Search.name))
    return list(result.scalars().all())


async def _validate_account(session: DbSession, account_id: uuid.UUID | None) -> None:
    if account_id is None:
        return
    from app.db.models import AvitoAccount

    account = await session.get(AvitoAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    if account.role == "seller":
        raise HTTPException(
            status_code=422,
            detail="аккаунт продавца нельзя привязать к поиску — выберите «поисковик»",
        )


@router.post("", response_model=SearchRead, status_code=201)
async def create_search(payload: SearchCreate, session: DbSession) -> Search:
    await _validate_account(session, payload.account_id)
    search = Search(**payload.model_dump())
    session.add(search)
    await session.commit()
    await session.refresh(search)
    return search


@router.patch("/{search_id}", response_model=SearchRead)
async def update_search(search_id: uuid.UUID, payload: SearchUpdate, session: DbSession) -> Search:
    search = await session.get(Search, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="search not found")
    data = payload.model_dump(exclude_unset=True)
    if "account_id" in data:
        await _validate_account(session, data["account_id"])
    if isinstance(data.get("params"), dict):
        # PATCH params — частичное обновление: не теряем фильтры, не переданные в запросе.
        data["params"] = merge_params(search.params, data["params"])
    for field, value in data.items():
        setattr(search, field, value)
    await session.commit()
    await session.refresh(search)
    return search


@router.delete("/{search_id}", status_code=204)
async def delete_search(search_id: uuid.UUID, session: DbSession) -> None:
    search = await session.get(Search, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="search not found")
    # Алерты ссылаются на поиск внутри payload (JSONB) — удаляем вместе с поиском,
    # иначе «сироты» всплывают в API/панели и ведут на удалённый поиск.
    await session.execute(delete(Alert).where(Alert.payload["search_id"].astext == str(search_id)))
    await session.delete(search)
    await session.commit()


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
        await CrawlProgress(redis, search_id).queued(search.name)
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


SORT_OPTIONS = ("position", "price_asc", "price_desc", "new", "status")


def _order_by(sort: str) -> list:
    if sort == "price_asc":
        return [Listing.current_price.asc().nulls_last(), SearchListing.last_position]
    if sort == "price_desc":
        return [Listing.current_price.desc().nulls_last(), SearchListing.last_position]
    if sort == "new":
        return [SearchListing.first_seen.desc(), SearchListing.last_position]
    if sort == "status":
        return [Listing.status, SearchListing.last_position]
    return [SearchListing.last_position.nulls_last()]


@router.get("/{search_id}/listings", response_model=list[ListingRead])
async def list_search_listings(
    search_id: uuid.UUID,
    session: DbSession,
    limit: int = 0,
    flagged: bool | None = None,
    category: str | None = None,
    excluded: bool | None = None,
    region: str | None = None,
    sort: str = "position",
    fresh: bool | None = None,
    offset: int = 0,
    seller: str | None = None,
) -> list[ListingRead]:
    """Выдача поиска. ``limit=0`` — без лимита; ``sort`` — цена/позиция/новизна/статус."""
    search = await session.get(Search, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="search not found")
    params = search.params if isinstance(search.params, dict) else {}
    groups = keywords_from_params(search.params)
    excludes = exclude_keywords_from_params(search.params)
    regions = regions_from_params(search.params)
    exclude_regions = exclude_regions_from_params(search.params)
    target_refs = seller_refs_from_params(search.params, TARGET_KEY)
    exclude_refs = seller_refs_from_params(search.params, EXCLUDE_KEY)
    max_age_days = params.get("max_age_days")

    statement = (
        select(
            Listing.id,
            Listing.title,
            Listing.current_price,
            Listing.url,
            Listing.status,
            SearchListing.last_position,
            Listing.is_flagged,
            Listing.flag_reasons,
            Listing.relevance_score,
            Listing.flag_category,
            Listing.description,
            Listing.region,
            ListingExclusion.listing_id,
            SearchListing.first_seen,
            Seller.name,
            Seller.url,
        )
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .outerjoin(
            ListingExclusion,
            (ListingExclusion.listing_id == Listing.id) & (ListingExclusion.search_id == search_id),
        )
        .outerjoin(Seller, Seller.id == Listing.seller_id)
        .where(SearchListing.search_id == search_id)
    )
    if flagged is not None:
        statement = statement.where(Listing.is_flagged.is_(flagged))
    if category:
        statement = statement.where(Listing.flag_category == category)
    if region:
        statement = statement.where(Listing.region == normalize_region(region))
    if (
        fresh
        and isinstance(max_age_days, int)
        and not isinstance(max_age_days, bool)
        and max_age_days > 0
    ):
        statement = statement.where(
            SearchListing.first_seen >= datetime.now(UTC) - timedelta(days=max_age_days)
        )
    statement = statement.order_by(*_order_by(sort if sort in SORT_OPTIONS else "position"))
    safe_offset = max(0, offset)
    if limit > 0 and excluded is None:
        statement = statement.limit(limit).offset(safe_offset)
    rows = await session.execute(statement)

    items: list[ListingRead] = []
    for row in rows.all():
        text = combined_text(row[1] or "", row[10])
        listing_region = row[11]
        manual_excluded = row[12] is not None
        seller_name = row[14]
        seller_url = row[15]
        detail: str | None = None
        if manual_excluded:
            reason: str | None = "manual"
        elif groups and (missing := first_missing_group(text, groups)):
            reason = "keyword"
            detail = f"нет: {', '.join(missing[:3])}"
        elif word := first_matching_exclude(text, excludes):
            reason = "stopword"
            detail = word
        elif (target_refs or exclude_refs) and (
            seller_reason := seller_filter_reason(
                name=seller_name,
                url=seller_url,
                target_refs=target_refs,
                exclude_refs=exclude_refs,
            )
        ) is not None:
            reason = "seller"
            detail = "исключён" if seller_reason == "excluded" else "не целевой"
        elif not matches_region(listing_region, regions, exclude_regions):
            reason = "region"
            detail = listing_region
        else:
            reason = None
        if seller and not ref_matches_seller(seller, name=seller_name, url=seller_url):
            continue
        items.append(
            ListingRead(
                id=row[0],
                title=row[1],
                price=float(row[2]) if row[2] is not None else None,
                url=row[3],
                status=row[4],
                last_position=row[5],
                is_flagged=bool(row[6]),
                flag_reasons=row[7],
                relevance_score=float(row[8]) if row[8] is not None else None,
                flag_category=row[9],
                description_snippet=(row[10][:400] if row[10] else None),
                region=listing_region,
                manual_excluded=manual_excluded,
                seller_name=seller_name,
                seller_url=seller_url,
                exclude_reason=reason,
                exclude_detail=detail,
                excluded=reason is not None,
                first_seen=row[13],
            )
        )
    if excluded is not None:
        items = [item for item in items if item.excluded == excluded]
        if limit > 0:
            items = items[safe_offset : safe_offset + limit]
    return items


class SearchSellerOut(BaseModel):
    seller_id: int | None
    name: str | None
    url: str | None
    count: int


class SearchSellersOut(BaseModel):
    sellers: list[SearchSellerOut]
    target_refs: list[str]
    exclude_refs: list[str]


class SellerRefIn(BaseModel):
    ref: str = Field(min_length=1, max_length=300)
    mode: Literal["target", "exclude", "remove_target", "remove_exclude"] = "target"


async def _search_sellers(session: DbSession, search: Search) -> SearchSellersOut:
    rows = await session.execute(
        select(Listing.seller_id, Seller.name, Seller.url, func.count())
        .select_from(Listing)
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .outerjoin(Seller, Seller.id == Listing.seller_id)
        .where(SearchListing.search_id == search.id, Listing.status == "active")
        .group_by(Listing.seller_id, Seller.name, Seller.url)
        .order_by(func.count().desc())
        .limit(500)
    )
    sellers = [
        SearchSellerOut(seller_id=row[0], name=row[1], url=row[2], count=int(row[3] or 0))
        for row in rows.all()
        if row[1] or row[2]
    ]
    return SearchSellersOut(
        sellers=sellers,
        target_refs=seller_refs_from_params(search.params, TARGET_KEY),
        exclude_refs=seller_refs_from_params(search.params, EXCLUDE_KEY),
    )


@router.get("/{search_id}/sellers", response_model=SearchSellersOut)
async def list_search_sellers(search_id: uuid.UUID, session: DbSession) -> SearchSellersOut:
    """Продавцы выдачи поиска + списки целевых/исключённых."""
    search = await session.get(Search, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="search not found")
    return await _search_sellers(session, search)


@router.post("/{search_id}/sellers", response_model=SearchSellersOut)
async def update_search_seller(
    search_id: uuid.UUID, payload: SellerRefIn, session: DbSession
) -> SearchSellersOut:
    """Добавляет/убирает продавца в целевые или исключённые (ссылка или имя)."""
    search = await session.get(Search, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="search not found")
    params = dict(search.params) if isinstance(search.params, dict) else {}
    target = seller_refs_from_params(params, TARGET_KEY)
    exclude = seller_refs_from_params(params, EXCLUDE_KEY)
    ref = payload.ref.strip()
    if payload.mode == "target":
        if ref not in target:
            target.append(ref)
        exclude = [item for item in exclude if item != ref]
    elif payload.mode == "exclude":
        if ref not in exclude:
            exclude.append(ref)
        target = [item for item in target if item != ref]
    elif payload.mode == "remove_target":
        target = [item for item in target if item != ref]
    else:
        exclude = [item for item in exclude if item != ref]
    if target:
        params[TARGET_KEY] = target
    else:
        params.pop(TARGET_KEY, None)
    if exclude:
        params[EXCLUDE_KEY] = exclude
    else:
        params.pop(EXCLUDE_KEY, None)
    search.params = params
    await session.commit()
    return await _search_sellers(session, search)


class ExclusionsRequest(BaseModel):
    listing_ids: list[int] = Field(min_length=1, max_length=10_000)
    excluded: bool = True
    reason: str | None = "вручную"


class ListingsStatsOut(BaseModel):
    total: int
    excluded: int
    fresh: int
    max_age_days: int
    regions: list[dict]


@router.get("/{search_id}/listings/stats", response_model=ListingsStatsOut)
async def listings_stats(search_id: uuid.UUID, session: DbSession) -> ListingsStatsOut:
    # Лёгкая статистика выдачи: всего/исключено/свежих и регионы (чипы и фильтры).
    search = await session.get(Search, search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="search not found")
    params = search.params if isinstance(search.params, dict) else {}
    groups = keywords_from_params(search.params)
    excludes = exclude_keywords_from_params(search.params)
    regions_filter = regions_from_params(search.params)
    exclude_regions = exclude_regions_from_params(search.params)
    raw_age = params.get("max_age_days")
    max_age_days = (
        raw_age if isinstance(raw_age, int) and not isinstance(raw_age, bool) and raw_age > 0 else 0
    )
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days) if max_age_days else None

    rows = await session.execute(
        select(
            Listing.title,
            Listing.region,
            SearchListing.first_seen,
            ListingExclusion.listing_id,
            Listing.description,
        )
        .join(SearchListing, SearchListing.listing_id == Listing.id)
        .outerjoin(
            ListingExclusion,
            (ListingExclusion.listing_id == Listing.id) & (ListingExclusion.search_id == search_id),
        )
        .where(SearchListing.search_id == search_id)
    )
    total = 0
    excluded = 0
    fresh = 0
    region_counts: dict[str, int] = {}
    for title, listing_region, first_seen, manual_id, description in rows.all():
        total += 1
        if listing_region:
            region_counts[listing_region] = region_counts.get(listing_region, 0) + 1
        if cutoff is not None and first_seen is not None and first_seen >= cutoff:
            fresh += 1
        if manual_id is not None:
            excluded += 1
            continue
        text = combined_text(title or "", description)
        if groups and not matches_keyword_groups(text, groups):
            excluded += 1
            continue
        if matches_exclude_keywords(text, excludes):
            excluded += 1
            continue
        if not matches_region(listing_region, regions_filter, exclude_regions):
            excluded += 1
    return ListingsStatsOut(
        total=total,
        excluded=excluded,
        fresh=fresh,
        max_age_days=max_age_days,
        regions=[
            {"region": region, "count": count}
            for region, count in sorted(region_counts.items(), key=lambda item: -item[1])
        ],
    )


@router.post("/{search_id}/listings/exclusions")
async def set_listing_exclusions(
    search_id: uuid.UUID, payload: ExclusionsRequest, session: DbSession
) -> dict[str, object]:
    """Ручное исключение объявлений из расчёта (или возврат в расчёт)."""
    if await session.get(Search, search_id) is None:
        raise HTTPException(status_code=404, detail="search not found")
    existing = set(
        (await session.execute(select(Listing.id).where(Listing.id.in_(payload.listing_ids))))
        .scalars()
        .all()
    )
    ids = [listing_id for listing_id in payload.listing_ids if listing_id in existing]
    if payload.excluded:
        if ids:
            statement = (
                pg_insert(ListingExclusion)
                .values(
                    [
                        {"search_id": search_id, "listing_id": listing_id, "reason": payload.reason}
                        for listing_id in ids
                    ]
                )
                .on_conflict_do_nothing()
            )
            await session.execute(statement)
    elif ids:
        await session.execute(
            delete(ListingExclusion).where(
                ListingExclusion.search_id == search_id,
                ListingExclusion.listing_id.in_(ids),
            )
        )
    await session.commit()
    total = await session.scalar(
        select(func.count())
        .select_from(ListingExclusion)
        .where(ListingExclusion.search_id == search_id)
    )
    return {
        "excluded": payload.excluded,
        "updated": len(ids),
        "total_excluded": int(total or 0),
    }


class ModerateOut(BaseModel):
    total: int
    flagged: int
    ai_scored: int
    described: int
    median: float | None
    categories: dict[str, int]


@router.post("/{search_id}/moderate", response_model=ModerateOut)
async def run_moderation(search_id: uuid.UUID, session: DbSession) -> ModerateOut:
    if await session.get(Search, search_id) is None:
        raise HTTPException(status_code=404, detail="search not found")
    from app.services.moderation import moderate_search

    result = await moderate_search(session, search_id)
    await session.commit()
    return ModerateOut(
        total=result.total,
        flagged=result.flagged,
        ai_scored=result.ai_scored,
        described=result.described,
        median=result.median,
        categories=result.categories,
    )
