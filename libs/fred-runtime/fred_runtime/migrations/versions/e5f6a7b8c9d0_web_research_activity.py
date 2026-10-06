# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Add restricted web research activity records."""

import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d0"  # pragma: allowlist secret
down_revision = "d4e5c6b7a8f9"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_web_research_activity_gate",
        sa.Column("subject_hash", sa.String(64), primary_key=True),
        sa.Column("erased", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "runtime_web_research_activity",
        sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("session_id", sa.String(128)),
        sa.Column("team_id", sa.String(128)),
        sa.Column("agent_instance_id", sa.String(128)),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("query", sa.Text()),
        sa.Column("url", sa.Text()),
        sa.Column("final_url", sa.Text()),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("result_count", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_runtime_web_research_activity_user_id",
        "runtime_web_research_activity",
        ["user_id"],
    )
    op.create_index(
        "ix_runtime_web_research_activity_expires_at",
        "runtime_web_research_activity",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_table("runtime_web_research_activity")
    op.drop_table("runtime_web_research_activity_gate")
