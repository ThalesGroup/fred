"""initial schema

Matches the production database as of 2026-03-26.

Revision ID: 8e5a41c87864
Revises:
Create Date: 2026-03-26 17:26:03.512104

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8e5a41c87864"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "mcp-server",
        sa.Column("server_id", sa.String(), nullable=False),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("server_id"),
    )
    op.create_table(
        "session",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("agent_id", sa.String(), nullable=True),
        sa.Column(
            "session_data", sa.JSON().with_variant(sa.JSON(), "sqlite"), nullable=True
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index(op.f("ix_session_agent_id"), "session", ["agent_id"], unique=False)
    op.create_index(
        op.f("ix_session_updated_at"), "session", ["updated_at"], unique=False
    )
    op.create_index(op.f("ix_session_user_id"), "session", ["user_id"], unique=False)
    op.create_table(
        "session_attachments",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("attachment_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("mime", sa.String(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("summary_md", sa.Text(), nullable=False),
        sa.Column("document_uid", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id", "attachment_id"),
    )
    op.create_table(
        "session_history",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("exchange_id", sa.String(), nullable=True),
        sa.Column(
            "parts_json",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("session_id", "user_id", "rank"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("session_history")
    op.drop_table("session_attachments")
    op.drop_index(op.f("ix_session_user_id"), table_name="session")
    op.drop_index(op.f("ix_session_updated_at"), table_name="session")
    op.drop_index(op.f("ix_session_agent_id"), table_name="session")
    op.drop_table("session")
    op.drop_table("mcp-server")
    op.drop_table("agent")
