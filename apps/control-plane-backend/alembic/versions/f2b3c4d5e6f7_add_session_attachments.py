"""add session attachments

Revision ID: f2b3c4d5e6f7
Revises: be753abe25d7
Create Date: 2026-06-11 12:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "f2b3c4d5e6f7"  # pragma: allowlist secret
down_revision = "b4c5d6e7f8a9"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_attachments",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("attachment_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("mime", sa.String(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("summary_md", sa.Text(), nullable=False),
        sa.Column("document_uid", sa.String(), nullable=True),
        sa.Column("storage_key", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id", "attachment_id"),
    )


def downgrade() -> None:
    op.drop_table("session_attachments")
