"""Add short-lived authorized source views for sandbox mounts.

Revision ID: 6a8c9d2e4f10
Revises: 02d556a6f182
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "6a8c9d2e4f10"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "02d556a6f182"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sandbox_file_views",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("bytes_served", sa.Integer(), nullable=False),
        sa.Column("request_window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_window_count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_sandbox_file_views_session_id", "sandbox_file_views", ["session_id"])
    op.create_index("ix_sandbox_file_views_expires_at", "sandbox_file_views", ["expires_at"])
    op.create_table(
        "sandbox_attachment_originals",
        sa.Column("document_uid", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_sandbox_attachment_originals_session_id",
        "sandbox_attachment_originals",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_sandbox_attachment_originals_session_id", table_name="sandbox_attachment_originals")
    op.drop_table("sandbox_attachment_originals")
    op.drop_index("ix_sandbox_file_views_expires_at", table_name="sandbox_file_views")
    op.drop_index("ix_sandbox_file_views_session_id", table_name="sandbox_file_views")
    op.drop_table("sandbox_file_views")
