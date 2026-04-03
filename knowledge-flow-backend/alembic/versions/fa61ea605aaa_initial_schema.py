"""initial schema

Revision ID: fa61ea605aaa
Revises:
Create Date: 2026-04-01 19:34:04.046654

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fa61ea605aaa"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "resource",
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("resource_name", sa.String(), nullable=True),
        sa.Column("resource_type", sa.String(), nullable=True),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("doc", postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"), nullable=True),
        sa.PrimaryKeyConstraint("resource_id"),
    )
    op.create_index(op.f("ix_resource_author"), "resource", ["author"], unique=False)
    op.create_index(op.f("ix_resource_resource_name"), "resource", ["resource_name"], unique=False)
    op.create_index(op.f("ix_resource_resource_type"), "resource", ["resource_type"], unique=False)
    op.create_table(
        "tag",
        sa.Column("tag_id", sa.String(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True).with_variant(sa.DateTime(timezone=True), "sqlite"), nullable=True),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True).with_variant(sa.DateTime(timezone=True), "sqlite"), nullable=True),
        sa.Column("owner_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("path", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("type", sa.String(), nullable=True),
        sa.Column("doc", postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"), nullable=True),
        sa.PrimaryKeyConstraint("tag_id"),
    )
    op.create_index(op.f("ix_tag_name"), "tag", ["name"], unique=False)
    op.create_index(op.f("ix_tag_owner_id"), "tag", ["owner_id"], unique=False)
    op.create_index(op.f("ix_tag_path"), "tag", ["path"], unique=False)
    op.create_index(op.f("ix_tag_type"), "tag", ["type"], unique=False)
    op.create_index(op.f("ix_tag_updated_at"), "tag", ["updated_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_tag_updated_at"), table_name="tag")
    op.drop_index(op.f("ix_tag_type"), table_name="tag")
    op.drop_index(op.f("ix_tag_path"), table_name="tag")
    op.drop_index(op.f("ix_tag_owner_id"), table_name="tag")
    op.drop_index(op.f("ix_tag_name"), table_name="tag")
    op.drop_table("tag")
    op.drop_index(op.f("ix_resource_resource_type"), table_name="resource")
    op.drop_index(op.f("ix_resource_resource_name"), table_name="resource")
    op.drop_index(op.f("ix_resource_author"), table_name="resource")
    op.drop_table("resource")
