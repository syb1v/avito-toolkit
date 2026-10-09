"""listing edits: AI summary

Revision ID: 0015_edit_ai_summary
Revises: 0014_listing_edits
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_edit_ai_summary"
down_revision = "0014_listing_edits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listing_edits", sa.Column("ai_summary", sa.Text()))


def downgrade() -> None:
    op.drop_column("listing_edits", "ai_summary")
