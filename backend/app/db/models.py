import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AvitoAccount(Base):
    __tablename__ = "avito_accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    profile_dir: Mapped[str] = mapped_column(Text, unique=True)
    # searcher — обход выдачи; seller — управление своими объявлениями (фаза 6)
    role: Mapped[str] = mapped_column(String(20), default="searcher")
    # Закреплённый прокси аккаунта (sticky): cookies доверяют вместе с выходным IP.
    # NULL — ходить с личного IP (BROWSER_* / PROXY_ENABLED=false).
    proxy_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")
    notes: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    cookies_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Proxy(Base):
    """Прокси, управляемый из UI (env PROXY_LIST используется как сид)."""

    __tablename__ = "proxies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(Text, unique=True)
    note: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text)
    params: Mapped[dict | None] = mapped_column(JSONB)
    schedule_cron: Mapped[str] = mapped_column(String(64), default="*/30 * * * *")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("avito_accounts.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Seller(Base):
    __tablename__ = "sellers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(Text)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    seller_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sellers.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(255))
    params: Mapped[dict | None] = mapped_column(JSONB)
    current_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(32), default="active")
    url: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    description_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_category: Mapped[str | None] = mapped_column(String(32))
    flag_reasons: Mapped[list | None] = mapped_column(JSONB)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SearchListing(Base):
    __tablename__ = "search_listings"

    search_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("searches.id", ondelete="CASCADE"), primary_key=True
    )
    listing_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_position: Mapped[int | None] = mapped_column(Integer)


class ListingExclusion(Base):
    """Ручное исключение объявления из расчёта по конкретному поиску."""

    __tablename__ = "listing_exclusions"

    search_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("searches.id", ondelete="CASCADE"), primary_key=True
    )
    listing_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ListingSnapshot(Base):
    __tablename__ = "listing_snapshots"

    search_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    listing_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    position_index: Mapped[int | None] = mapped_column(Integer)
    is_vip: Mapped[bool] = mapped_column(Boolean, default=False)
    is_highlighted: Mapped[bool] = mapped_column(Boolean, default=False)


class MarketAnalyticsDaily(Base):
    __tablename__ = "market_analytics_daily"

    search_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    calc_date: Mapped[date] = mapped_column(Date, primary_key=True)
    active_count: Mapped[int] = mapped_column(Integer, default=0)
    new_today_count: Mapped[int] = mapped_column(Integer, default=0)
    delisted_today_count: Mapped[int] = mapped_column(Integer, default=0)
    price_min: Mapped[float | None] = mapped_column(Numeric(12, 2))
    price_max: Mapped[float | None] = mapped_column(Numeric(12, 2))
    price_median: Mapped[float | None] = mapped_column(Numeric(12, 2))
    price_p25: Mapped[float | None] = mapped_column(Numeric(12, 2))
    price_p75: Mapped[float | None] = mapped_column(Numeric(12, 2))
    avg_lifetime_days: Mapped[float | None] = mapped_column(Numeric(5, 1))


class ProductMarketMatch(Base):
    __tablename__ = "product_market_matches"

    our_sku_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    market_listing_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    similarity_score: Mapped[float] = mapped_column(Float, default=0.0)
    match_status: Mapped[str] = mapped_column(String(20), default="auto_matched")
    matched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OurListing(Base):
    __tablename__ = "our_listings"

    sku: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    cost_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    category: Mapped[str | None] = mapped_column(String(255))
    account: Mapped[str | None] = mapped_column(String(64))
    params: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avito_item_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    avito_status: Mapped[str | None] = mapped_column(String(32))
    avito_url: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ListingEdit(Base):
    """Черновик/факт правки цены своего объявления через кабинет продавца."""

    __tablename__ = "listing_edits"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sku: Mapped[str] = mapped_column(
        String(64), ForeignKey("our_listings.sku", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("avito_accounts.id", ondelete="SET NULL")
    )
    old_price: Mapped[float] = mapped_column(Numeric(12, 2))
    target_price: Mapped[float] = mapped_column(Numeric(12, 2))
    delta_pct: Mapped[float] = mapped_column(Float, default=0.0)
    strategy: Mapped[str] = mapped_column(String(32), default="keep_current")
    # draft | approved | rejected | applying | applied | reverting | reverted | failed
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    mode: Mapped[str] = mapped_column(String(12), default="dry_run")
    error: Mapped[str | None] = mapped_column(Text)
    screenshot_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reverted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    payload: Mapped[dict | None] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiDigest(Base):
    """Сохранённый AI-дайджест поиска: виден всем, не нужно генерировать заново."""

    __tablename__ = "ai_digests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    search_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("searches.id", ondelete="CASCADE"), index=True
    )
    payload: Mapped[dict] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LlmRun(Base):
    __tablename__ = "llm_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(32), default="v1")
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    actor: Mapped[str] = mapped_column(String(128), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
