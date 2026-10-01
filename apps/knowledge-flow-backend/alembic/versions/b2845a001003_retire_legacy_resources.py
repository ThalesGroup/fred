"""Retire legacy knowledge-flow resources without discarding existing data.

Revision ID: b2845a001003
Revises: b2845a001002
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "b2845a001003"
down_revision = "b2845a001002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM resource LIMIT 1")).first():
        raise RuntimeError("Legacy resources remain: export and review their disposition before upgrading.")
    if connection.execute(sa.text("SELECT 1 FROM tag WHERE type IS NULL OR type <> 'document' LIMIT 1")).first():
        raise RuntimeError("Legacy non-document folders remain: review their disposition before upgrading.")
    op.drop_table("resource")


def downgrade() -> None:
    op.create_table(
        "resource",
        sa.Column("resource_id", sa.String(), primary_key=True),
        sa.Column("resource_name", sa.String(), nullable=True),
        sa.Column("resource_type", sa.String(), nullable=True),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("doc", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), nullable=True),
    )
    for column in ("resource_name", "resource_type", "author"):
        op.create_index(f"ix_resource_{column}", "resource", [column])
