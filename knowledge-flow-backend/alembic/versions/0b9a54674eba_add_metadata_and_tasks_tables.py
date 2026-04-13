"""add metadata and tasks tables

Revision ID: 0b9a54674eba
Revises: fa61ea605aaa
Create Date: 2026-04-01 19:34:04.046654

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0b9a54674eba"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "fa61ea605aaa"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "metadata",
        sa.Column("document_uid", sa.String(), nullable=False),
        sa.Column("source_tag", sa.String(), nullable=True),
        sa.Column("date_added_to_kb", postgresql.TIMESTAMP(timezone=True).with_variant(sa.DateTime(timezone=True), "sqlite"), nullable=True),
        sa.Column("tag_ids", postgresql.ARRAY(sa.String()).with_variant(sa.JSON(), "sqlite"), nullable=True),
        sa.Column("doc", postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"), nullable=True),
        sa.PrimaryKeyConstraint("document_uid"),
    )
    op.create_index("idx_metadata_tag_ids_gin", "metadata", ["tag_ids"], unique=False, postgresql_using="gin")
    op.create_index(op.f("ix_metadata_source_tag"), "metadata", ["source_tag"], unique=False)
    op.create_table(
        "sched_workflow_tasks",
        sa.Column("workflow_id", sa.String(), nullable=False),
        sa.Column("current_document_uid", sa.String(), nullable=True),
        sa.Column("current_filename", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True).with_variant(sa.DateTime(timezone=True), "sqlite"), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True).with_variant(sa.DateTime(timezone=True), "sqlite"), nullable=False),
        sa.PrimaryKeyConstraint("workflow_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("sched_workflow_tasks")
    op.drop_index(op.f("ix_metadata_source_tag"), table_name="metadata")
    op.drop_index("idx_metadata_tag_ids_gin", table_name="metadata", postgresql_using="gin")
    op.drop_table("metadata")
