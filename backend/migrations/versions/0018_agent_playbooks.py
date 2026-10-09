"""agent playbooks

Revision ID: 0018_agent_playbooks
Revises: 0017_ai_center
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018_agent_playbooks"
down_revision = "0017_ai_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_playbooks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("criteria", JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("agent_playbooks")
