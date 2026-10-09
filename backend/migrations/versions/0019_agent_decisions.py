"""agent decisions journal

Revision ID: 0019_agent_decisions
Revises: 0018_agent_playbooks
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0019_agent_decisions"
down_revision = "0018_agent_playbooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("payload", JSONB(), nullable=False, server_default="{}"),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("agent_decisions")
