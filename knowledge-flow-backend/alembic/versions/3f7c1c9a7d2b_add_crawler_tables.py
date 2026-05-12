"""add crawler tables

Revision ID: 3f7c1c9a7d2b
Revises: 0b9a54674eba
Create Date: 2026-04-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "3f7c1c9a7d2b"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "0b9a54674eba"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    json_type = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")
    ts_type = postgresql.TIMESTAMP(timezone=True).with_variant(sa.DateTime(timezone=True), "sqlite")

    op.create_table(
        "crawl_source",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", ts_type, nullable=False),
        sa.Column("doc", json_type, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_crawl_source_workspace_id"), "crawl_source", ["workspace_id"], unique=False)
    op.create_index(op.f("ix_crawl_source_status"), "crawl_source", ["status"], unique=False)

    op.create_table(
        "crawl_run",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", ts_type, nullable=True),
        sa.Column("finished_at", ts_type, nullable=True),
        sa.Column("doc", json_type, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_crawl_run_source_id"), "crawl_run", ["source_id"], unique=False)
    op.create_index(op.f("ix_crawl_run_status"), "crawl_run", ["status"], unique=False)

    op.create_table(
        "crawl_url",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("normalized_url", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("next_eligible_at", ts_type, nullable=False),
        sa.Column("doc", json_type, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "normalized_url", name="uq_crawl_url_run_url"),
    )
    op.create_index(op.f("ix_crawl_url_run_id"), "crawl_url", ["run_id"], unique=False)
    op.create_index(op.f("ix_crawl_url_normalized_url"), "crawl_url", ["normalized_url"], unique=False)
    op.create_index(op.f("ix_crawl_url_status"), "crawl_url", ["status"], unique=False)
    op.create_index(op.f("ix_crawl_url_next_eligible_at"), "crawl_url", ["next_eligible_at"], unique=False)

    op.create_table(
        "crawl_page_version",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("normalized_url", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("fetched_at", ts_type, nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("doc", json_type, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_url", "content_hash", name="uq_crawl_page_version_url_hash"),
    )
    op.create_index(op.f("ix_crawl_page_version_run_id"), "crawl_page_version", ["run_id"], unique=False)
    op.create_index(op.f("ix_crawl_page_version_normalized_url"), "crawl_page_version", ["normalized_url"], unique=False)
    op.create_index(op.f("ix_crawl_page_version_content_hash"), "crawl_page_version", ["content_hash"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_crawl_page_version_content_hash"), table_name="crawl_page_version")
    op.drop_index(op.f("ix_crawl_page_version_normalized_url"), table_name="crawl_page_version")
    op.drop_index(op.f("ix_crawl_page_version_run_id"), table_name="crawl_page_version")
    op.drop_table("crawl_page_version")
    op.drop_index(op.f("ix_crawl_url_next_eligible_at"), table_name="crawl_url")
    op.drop_index(op.f("ix_crawl_url_status"), table_name="crawl_url")
    op.drop_index(op.f("ix_crawl_url_normalized_url"), table_name="crawl_url")
    op.drop_index(op.f("ix_crawl_url_run_id"), table_name="crawl_url")
    op.drop_table("crawl_url")
    op.drop_index(op.f("ix_crawl_run_status"), table_name="crawl_run")
    op.drop_index(op.f("ix_crawl_run_source_id"), table_name="crawl_run")
    op.drop_table("crawl_run")
    op.drop_index(op.f("ix_crawl_source_status"), table_name="crawl_source")
    op.drop_index(op.f("ix_crawl_source_workspace_id"), table_name="crawl_source")
    op.drop_table("crawl_source")
