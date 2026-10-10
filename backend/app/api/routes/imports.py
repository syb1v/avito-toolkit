"""Импорт поисков из выгрузки Авито (xlsx): загрузка, AI-фильтры, создание поисков."""

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import func, select

from app.ai.client import LlmNotConfiguredError
from app.ai.prompts import SEARCH_FILTERS_VERSION
from app.ai.runs import record_llm_run
from app.ai.tasks import generate_search_filters
from app.api.deps import DbSession
from app.config import get_settings
from app.db.models import AvitoAccount, OurListing, Search
from app.services.import_file import (
    FileRow,
    fallback_query,
    load_staging,
    parse_xlsx,
    save_staging,
    search_params,
    search_url,
    validate_generated_filter,
)
from app.services.matching import match_our_listing
from app.services.our_listings import ImportRow, sku_for_item, upsert_our_listings
from app.services.web_research import research_product_identity

router = APIRouter(prefix="/searches/import-file", tags=["searches-import"])

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ITEMS = 20
FILTER_BATCH_SIZE = 5
DEFAULT_CRON = "0 4 * * *"


class ImportFileOut(BaseModel):
    token: str
    total: int
    rows: list[dict[str, Any]]


class FiltersIn(BaseModel):
    avito_ids: list[int] = Field(..., min_length=1)


class SearchFiltersOut(BaseModel):
    avito_id: int
    query: str
    keyword_groups: list[list[str]]
    exclude_keywords: list[str]
    generated: bool
    research_status: str = "not_run"
    research_sources: list[dict[str, str]] = Field(default_factory=list)


class FiltersOut(BaseModel):
    items: list[SearchFiltersOut]


class ApplyItem(BaseModel):
    avito_id: int
    title: str
    price: float = Field(..., gt=0)
    status: str | None = None
    query: str
    keyword_groups: list[list[str]] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)


class ApplyIn(BaseModel):
    items: list[ApplyItem] = Field(..., min_length=1)
    account_id: uuid.UUID | None = None
    schedule_cron: str = DEFAULT_CRON
    regions: list[str] = Field(default_factory=list)
    exclude_regions: list[str] = Field(default_factory=list)


class ApplyOut(BaseModel):
    created_searches: int
    created_listings: int
    updated_listings: int
    matched: int
    skipped: int


@router.post("", response_model=ImportFileOut)
async def upload_import_file(file: Annotated[UploadFile, File()]) -> ImportFileOut:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="пустой файл")
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="файл больше 10 МБ")
    try:
        rows = parse_xlsx(data)
    except Exception as error:  # noqa: BLE001 — понятная ошибка вместо 500
        raise HTTPException(
            status_code=422, detail=f"не удалось прочитать xlsx: {error}"
        ) from error
    if not rows:
        raise HTTPException(
            status_code=422,
            detail="в файле не найдены колонки Id/Title/Price (выгрузка объявлений Авито)",
        )
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        token = await save_staging(redis, rows)
    finally:
        await redis.aclose()
    return ImportFileOut(token=token, total=len(rows), rows=[row.to_dict() for row in rows])


async def _merge_filters(
    session: DbSession,
    result: Any,
    results: dict[int, SearchFiltersOut],
) -> None:
    await record_llm_run(
        session,
        task="search_filters",
        result=result,
        prompt_version=SEARCH_FILTERS_VERSION,
    )
    for decision in result.content.items:
        if decision.avito_id is None:
            continue
        results[decision.avito_id] = SearchFiltersOut(
            avito_id=decision.avito_id,
            query=decision.query,
            keyword_groups=decision.keyword_groups,
            exclude_keywords=decision.exclude_keywords,
            generated=True,
        )


class ApiAccountOut(BaseModel):
    id: uuid.UUID
    name: str
    items_count: int


class FromAccountIn(BaseModel):
    account_id: uuid.UUID | None = None


@router.get("/accounts", response_model=list[ApiAccountOut])
async def list_api_accounts(session: DbSession) -> list[ApiAccountOut]:
    """API-аккаунты-продавцы и число наших SKU по каждому (для источника импорта)."""
    accounts = (
        (
            await session.execute(
                select(AvitoAccount)
                .where(AvitoAccount.api_client_id.is_not(None))
                .order_by(AvitoAccount.name)
            )
        )
        .scalars()
        .all()
    )
    if not accounts:
        return []
    count_rows = await session.execute(
        select(OurListing.account_id, func.count())
        .where(
            OurListing.account_id.in_([account.id for account in accounts]),
            OurListing.avito_item_id.is_not(None),
        )
        .group_by(OurListing.account_id)
    )
    counts = {row[0]: int(row[1]) for row in count_rows.all()}
    return [
        ApiAccountOut(id=account.id, name=account.name, items_count=counts.get(account.id, 0))
        for account in accounts
    ]


@router.post("/from-account", response_model=ImportFileOut)
async def staging_from_account(payload: FromAccountIn, session: DbSession) -> ImportFileOut:
    """Строки для импорта берутся из наших SKU API-аккаунтов (а не из файла)."""
    if payload.account_id is not None:
        account = await session.get(AvitoAccount, payload.account_id)
        if account is None or not account.api_client_id:
            raise HTTPException(status_code=404, detail="API-аккаунт не найден")
        account_ids = [account.id]
    else:
        account_ids = [
            account.id
            for account in (
                await session.execute(
                    select(AvitoAccount).where(AvitoAccount.api_client_id.is_not(None))
                )
            )
            .scalars()
            .all()
        ]
    if not account_ids:
        raise HTTPException(status_code=404, detail="нет API-аккаунтов — добавьте аккаунт по ключу")
    listings = (
        (
            await session.execute(
                select(OurListing)
                .where(
                    OurListing.account_id.in_(account_ids),
                    OurListing.avito_item_id.is_not(None),
                    OurListing.is_active.is_(True),
                )
                .order_by(OurListing.title)
            )
        )
        .scalars()
        .all()
    )
    rows = [
        FileRow(
            avito_id=int(listing.avito_item_id or 0),
            title=listing.title,
            price=float(listing.price),
            status=listing.avito_status,
            category=None,
        )
        for listing in listings
        if (listing.avito_item_id or 0) > 0 and float(listing.price) > 0
    ]
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="у API-аккаунтов ещё нет товаров в базе — импортируйте их из файла один раз",
        )
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        token = await save_staging(redis, rows)
    finally:
        await redis.aclose()
    return ImportFileOut(token=token, total=len(rows), rows=[row.to_dict() for row in rows])


@router.post("/{token}/filters", response_model=FiltersOut)
async def generate_filters(token: str, payload: FiltersIn, session: DbSession) -> FiltersOut:
    """AI-фильтры для выбранных товаров (include-группы и слова-исключения)."""
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        rows = await load_staging(redis, token)
    finally:
        await redis.aclose()
    if rows is None:
        raise HTTPException(status_code=404, detail="файл не найден или устарел — загрузите заново")
    by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        row_id = row.get("avito_id")
        if isinstance(row_id, int):
            by_id[row_id] = row
    selected_ids = list(dict.fromkeys(payload.avito_ids))[:MAX_ITEMS]
    missing = [item for item in selected_ids if item not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"нет в файле: {missing[:5]}")

    research_by_id: dict[int, dict] = {}
    for item in selected_ids:
        research = await research_product_identity(str(by_id[item].get("title") or ""))
        research_by_id[item] = {
            "status": research.status,
            "sources": [{"url": source.url, "title": source.title} for source in research.sources],
        }

    results: dict[int, SearchFiltersOut] = {}
    configured = bool(settings.deepseek_api_key) and settings.llm_model.startswith("deepseek/")
    if configured:
        for start in range(0, len(selected_ids), FILTER_BATCH_SIZE):
            batch_ids = selected_ids[start : start + FILTER_BATCH_SIZE]
            items: list[tuple[int | None, str, str | None]] = []
            for item in batch_ids:
                raw_category = by_id[item].get("category")
                items.append(
                    (
                        item,
                        str(by_id[item].get("title") or ""),
                        raw_category if isinstance(raw_category, str) else None,
                    )
                )
            try:
                result = await generate_search_filters(
                    items=items, research={str(key): research_by_id[key] for key in batch_ids}
                )
            except LlmNotConfiguredError:
                configured = False
                break
            except Exception as error:  # noqa: BLE001 — обрезанный JSON и т.п.
                logger.warning("search filters batch failed (%s), retrying one by one", error)
                for single in items:
                    try:
                        single_id = single[0]
                        single_result = await generate_search_filters(
                            items=[single],
                            research=(
                                {str(single_id): research_by_id[single_id]}
                                if single_id is not None
                                else {}
                            ),
                        )
                    except LlmNotConfiguredError:
                        configured = False
                        break
                    except Exception as single_error:  # noqa: BLE001
                        logger.warning("search filters single failed: %s", single_error)
                        continue
                    await _merge_filters(session, single_result, results)
                if not configured:
                    break
                continue
            await _merge_filters(session, result, results)
    if configured:
        await session.commit()

    out: list[SearchFiltersOut] = []
    for item in selected_ids:
        found = results.get(item)
        if found is not None and validate_generated_filter(
            title=str(by_id[item].get("title") or ""),
            query=found.query,
            keyword_groups=found.keyword_groups,
            exclude_keywords=found.exclude_keywords,
        ):
            found.research_status = research_by_id[item]["status"]
            found.research_sources = research_by_id[item]["sources"]
            out.append(found)
        else:
            row = by_id[item]
            query = fallback_query(str(row.get("title") or ""))
            out.append(
                SearchFiltersOut(
                    avito_id=item,
                    query=query,
                    keyword_groups=[[query]],
                    exclude_keywords=[],
                    generated=False,
                )
            )
    return FiltersOut(items=out)


@router.post("/{token}/apply", response_model=ApplyOut)
async def apply_import(token: str, payload: ApplyIn, session: DbSession) -> ApplyOut:
    """Создаёт поиски и наши SKU по выбранным товарам (лимит 20 за раз)."""
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        rows = await load_staging(redis, token)
    finally:
        await redis.aclose()
    if rows is None:
        raise HTTPException(status_code=404, detail="файл не найден или устарел — загрузите заново")
    known_ids = {row_id for row in rows if isinstance(row_id := row.get("avito_id"), int)}
    items = payload.items[:MAX_ITEMS]
    if any(item.avito_id not in known_ids for item in items):
        raise HTTPException(status_code=422, detail="в запросе есть товары не из этого файла")

    account: AvitoAccount | None = None
    if payload.account_id is not None:
        account = await session.get(AvitoAccount, payload.account_id)
        if account is None or account.role != "seller":
            raise HTTPException(status_code=404, detail="аккаунт не найден")
    else:
        raise HTTPException(
            status_code=422,
            detail="выберите аккаунт-продавца перед применением импорта",
        )

    city = payload.regions[0] if len(payload.regions) == 1 else None
    existing_urls = {
        row[0]
        for row in (
            await session.execute(
                select(Search.url).where(
                    Search.url.in_([search_url(item.query, city) for item in items])
                )
            )
        ).all()
    }
    created_searches = skipped = 0
    import_rows: list[ImportRow] = []
    for item in items:
        url = search_url(item.query, city)
        if url in existing_urls:
            skipped += 1
            continue
        if payload.schedule_cron == DEFAULT_CRON and len(items) > 5:
            # распределяем обходы по минутам/часам, чтобы не бить одним залпом
            slot = created_searches
            schedule = f"{slot % 60} {2 + (slot // 60) % 20} * * *"
        else:
            schedule = payload.schedule_cron or DEFAULT_CRON
        session.add(
            Search(
                name=item.title[:255],
                url=url,
                params=search_params(
                    query=item.query,
                    keyword_groups=item.keyword_groups,
                    exclude_keywords=item.exclude_keywords,
                    regions=payload.regions,
                    exclude_regions=payload.exclude_regions,
                ),
                schedule_cron=schedule,
                priority=100,
                is_active=True,
                account_id=account.id if account is not None else None,
            )
        )
        existing_urls.add(url)
        created_searches += 1
        import_rows.append(
            ImportRow(
                sku=sku_for_item(item.avito_id),
                title=item.title,
                price=item.price,
                account=account.name if account is not None else None,
                account_id=account.id if account is not None else None,
                avito_item_id=item.avito_id,
                avito_url=None,
                avito_status=item.status or "active",
            )
        )
    listing_result = await upsert_our_listings(session, import_rows)
    await session.commit()
    matched = 0
    for row in import_rows:
        try:
            await match_our_listing(session, row.sku)
            matched += 1
        except Exception:  # noqa: BLE001 — матчинг не критичен
            continue
    await session.commit()
    return ApplyOut(
        created_searches=created_searches,
        created_listings=listing_result.created,
        updated_listings=listing_result.updated,
        matched=matched,
        skipped=skipped,
    )
