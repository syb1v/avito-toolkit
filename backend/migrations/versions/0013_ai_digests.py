"""persisted AI digests

Revision ID: 0013_ai_digests
Revises: 0012_proxies
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013_ai_digests"
down_revision = "0012_proxies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_digests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "search_id",
            sa.Uuid(),
            sa.ForeignKey("searches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("model", sa.String(128), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_ai_digests_search_id", "ai_digests", ["search_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_digests_search_id", table_name="ai_digests")
    op.drop_table("ai_digests")
