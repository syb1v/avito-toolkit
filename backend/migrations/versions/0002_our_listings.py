"""our_listings

Revision ID: 0002_our_listings
Revises: 0001_initial
Create Date: 2026-09-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_our_listings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "our_listings",
        sa.Column("sku", sa.String(64), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("cost_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("params", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_our_listings_category", "our_listings", ["category"])


def downgrade() -> None:
    op.drop_index("ix_our_listings_category", table_name="our_listings")
    op.drop_table("our_listings")
