"""ai artifacts, chat sessions, feedback

Revision ID: 0017_ai_center
Revises: 0016_accounts_api
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017_ai_center"
down_revision = "0016_accounts_api"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("model", sa.String(128), server_default=""),
        sa.Column("cost_usd", sa.Numeric(12, 6)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_ai_artifacts_kind_key", "ai_artifacts", ["kind", "key", "created_at"])

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False, server_default="Новый диалог"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(64)),
        sa.Column("tool_payload", JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_chat_messages_session", "chat_messages", ["session_id", "created_at"])

    op.create_table(
        "ai_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "artifact_id",
            sa.Uuid(),
            sa.ForeignKey("ai_artifacts.id", ondelete="SET NULL"),
        ),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_feedback")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("ai_artifacts")
