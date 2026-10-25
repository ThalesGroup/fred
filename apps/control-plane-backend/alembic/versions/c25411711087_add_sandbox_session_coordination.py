"""add sandbox session coordination

Revision ID: c25411711087
Revises: d0a1b2c3d4e5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c25411711087"  # pragma: allowlist secret
down_revision = "d0a1b2c3d4e5"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sandbox_conversation_leases",
        sa.Column("session_key", sa.String(64), primary_key=True),
        sa.Column("tenant_key", sa.String(64), nullable=False),
        sa.Column("workspace_id", sa.String(32), nullable=False, unique=True),
        sa.Column("view_epoch", sa.String(32), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("resource_name", sa.String(63), nullable=True),
        sa.Column("owner_token", sa.String(32), nullable=True),
        sa.Column("owner_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('new','preparing','running','suspending','suspended','resuming','deleting')",
            name="ck_sandbox_conversation_state",
        ),
    )
    op.create_index(
        "ix_sandbox_conversation_state_updated",
        "sandbox_conversation_leases",
        ["state", "updated_at"],
    )
    op.create_index(
        "ix_sandbox_conversation_last_used",
        "sandbox_conversation_leases",
        ["last_used_at"],
    )
    op.create_table(
        "sandbox_wait_tickets",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("session_key", sa.String(64), nullable=False),
        sa.Column("tenant_key", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_key"],
            ["sandbox_conversation_leases.session_key"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_sandbox_wait_order", "sandbox_wait_tickets", ["created_at", "id"]
    )
    op.create_index(
        "ix_sandbox_wait_tenant", "sandbox_wait_tickets", ["tenant_key"]
    )


def downgrade() -> None:
    op.drop_table("sandbox_wait_tickets")
    op.drop_table("sandbox_conversation_leases")
