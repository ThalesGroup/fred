# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Create space-owned corpus folders before offline document translation.

Revision ID: ef54a72b19d0
Revises: 02d556a6f182
"""

import sqlalchemy as sa
from alembic import op

revision = "ef54a72b19d0"
down_revision = "02d556a6f182"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corpus_folder",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("space_id", sa.String(), nullable=False),
        sa.Column("parent_id", sa.String()),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("source_version", sa.String()),
        sa.Column("synchronized_by", sa.String()),
        sa.UniqueConstraint("id", "space_id", name="uq_corpus_folder_id_space"),
        sa.UniqueConstraint("space_id", "parent_id", "name", name="uq_corpus_folder_sibling_name"),
        sa.ForeignKeyConstraint(["space_id"], ["space.id"], name="fk_corpus_folder_space"),
        sa.ForeignKeyConstraint(["parent_id", "space_id"], ["corpus_folder.id", "corpus_folder.space_id"], name="fk_corpus_folder_parent_space"),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_corpus_folder_parent"),
        sa.CheckConstraint("length(name) > 0 AND name = trim(name) AND name NOT LIKE '%/%' AND name NOT LIKE '%\\%' ESCAPE '!'", name="ck_corpus_folder_name"),
        sa.CheckConstraint("parent_id IS NULL OR (source_version IS NULL AND synchronized_by IS NULL)", name="ck_corpus_folder_root_source"),
    )
    op.create_index("uq_corpus_folder_root_name", "corpus_folder", ["space_id", "name"], unique=True, postgresql_where=sa.text("parent_id IS NULL"), sqlite_where=sa.text("parent_id IS NULL"))


def downgrade() -> None:
    op.drop_table("corpus_folder")
