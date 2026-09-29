"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE 'CREATE EXTENSION IF NOT EXISTS timescaledb';
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'timescaledb unavailable: %', SQLERRM;
        END
        $$;
        """
    )

    op.create_table(
        "searches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=True),
        sa.Column("schedule_cron", sa.String(64), nullable=False, server_default="*/30 * * * *"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "sellers",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "listings",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("seller_id", sa.BigInteger(), sa.ForeignKey("sellers.id", ondelete="SET NULL")),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("params", postgresql.JSONB(), nullable=True),
        sa.Column("current_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_listings_seller_id", "listings", ["seller_id"])
    op.create_index("ix_listings_category", "listings", ["category"])
    op.create_index("ix_listings_status", "listings", ["status"])

    op.create_table(
        "search_listings",
        sa.Column(
            "search_id",
            sa.Uuid(),
            sa.ForeignKey("searches.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "listing_id",
            sa.BigInteger(),
            sa.ForeignKey("listings.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_position", sa.Integer(), nullable=True),
    )
    op.create_index("ix_search_listings_listing_id", "search_listings", ["listing_id"])

    op.create_table(
        "listing_snapshots",
        sa.Column("search_id", sa.Uuid(), primary_key=True),
        sa.Column("listing_id", sa.BigInteger(), primary_key=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("position_index", sa.Integer(), nullable=True),
        sa.Column("is_vip", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "is_highlighted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.create_index(
        "ix_listing_snapshots_listing_time", "listing_snapshots", ["listing_id", "recorded_at"]
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
                PERFORM create_hypertable(
                    'listing_snapshots', 'recorded_at', if_not_exists => TRUE
                );
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
                ALTER TABLE listing_snapshots
                    SET (timescaledb.compress, timescaledb.compress_segmentby = 'listing_id');
                PERFORM add_compression_policy(
                    'listing_snapshots', INTERVAL '90 days', if_not_exists => TRUE
                );
            END IF;
        END
        $$;
        """
    )

    op.create_table(
        "market_analytics_daily",
        sa.Column(
            "search_id",
            sa.Uuid(),
            sa.ForeignKey("searches.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("calc_date", sa.Date(), primary_key=True),
        sa.Column("active_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_today_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delisted_today_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_min", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_max", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_median", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_p25", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_p75", sa.Numeric(12, 2), nullable=True),
        sa.Column("avg_lifetime_days", sa.Numeric(5, 1), nullable=True),
    )

    op.create_table(
        "product_market_matches",
        sa.Column("our_sku_id", sa.String(64), primary_key=True),
        sa.Column("market_listing_id", sa.BigInteger(), primary_key=True),
        sa.Column("similarity_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "match_status", sa.String(20), nullable=False, server_default="auto_matched"
        ),
        sa.Column("matched_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])

    op.create_table(
        "llm_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False, server_default="v1"),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_alerts_type", "alerts", ["type"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entity", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column("actor", sa.String(128), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_index("ix_alerts_type", table_name="alerts")
    op.drop_table("alerts")
    op.drop_table("llm_runs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("product_market_matches")
    op.drop_table("market_analytics_daily")
    op.drop_index("ix_listing_snapshots_listing_time", table_name="listing_snapshots")
    op.drop_table("listing_snapshots")
    op.drop_index("ix_search_listings_listing_id", table_name="search_listings")
    op.drop_table("search_listings")
    op.drop_index("ix_listings_status", table_name="listings")
    op.drop_index("ix_listings_category", table_name="listings")
    op.drop_index("ix_listings_seller_id", table_name="listings")
    op.drop_table("listings")
    op.drop_table("sellers")
    op.drop_table("searches")
