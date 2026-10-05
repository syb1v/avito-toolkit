"""seller listing edits

Revision ID: 0014_listing_edits
Revises: 0013_ai_digests
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_listing_edits"
down_revision = "0013_ai_digests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "listing_edits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "sku",
            sa.String(64),
            sa.ForeignKey("our_listings.sku", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("avito_accounts.id", ondelete="SET NULL"),
        ),
        sa.Column("old_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("target_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("delta_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("strategy", sa.String(32), nullable=False, server_default="keep_current"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("mode", sa.String(12), nullable=False, server_default="dry_run"),
        sa.Column("error", sa.Text()),
        sa.Column("screenshot_path", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("reverted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_listing_edits_sku", "listing_edits", ["sku"])
    op.create_index("ix_listing_edits_status", "listing_edits", ["status"])


def downgrade() -> None:
    op.drop_index("ix_listing_edits_status", table_name="listing_edits")
    op.drop_index("ix_listing_edits_sku", table_name="listing_edits")
    op.drop_table("listing_edits")
