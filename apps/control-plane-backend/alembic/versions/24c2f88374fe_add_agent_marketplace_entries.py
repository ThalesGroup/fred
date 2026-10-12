# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""add agent marketplace entries

One entry per published agent (snapshot, state, version), its configuration
files, and dated likes and imports kept across removal and republication.
Everything cascades with the agent; an import keeps its row when the agent it
created is deleted.

Revision ID: 24c2f88374fe
Revises: b5e1c9d3a7f2
Create Date: 2026-10-12 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "24c2f88374fe"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "b5e1c9d3a7f2"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

__all__ = [
    "branch_labels",
    "depends_on",
    "down_revision",
    "downgrade",
    "revision",
    "upgrade",
]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent_marketplace_entry",
        sa.Column("entry_id", sa.String(), nullable=False),
        sa.Column("agent_instance_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("removed_reason", sa.String(length=32), nullable=True),
        sa.Column("removed_message", sa.String(length=500), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("template_id", sa.String(), nullable=False),
        sa.Column("source_runtime_id", sa.String(), nullable=False),
        sa.Column("source_agent_id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("tuning_json", sa.Text(), nullable=False),
        sa.Column("capabilities_json", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("first_published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "snapshot_source_updated_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["agent_instance_id"],
            ["agent_instance.agent_instance_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("entry_id"),
        sa.UniqueConstraint("agent_instance_id"),
    )
    op.create_index(
        op.f("ix_agent_marketplace_entry_team_id"),
        "agent_marketplace_entry",
        ["team_id"],
        unique=False,
    )
    op.create_table(
        "agent_marketplace_entry_file",
        sa.Column("entry_id", sa.String(), nullable=False),
        sa.Column("capability_id", sa.String(), nullable=False),
        sa.Column("asset_key", sa.String(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["agent_marketplace_entry.entry_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("entry_id", "capability_id", "asset_key"),
    )
    op.create_table(
        "agent_marketplace_like",
        sa.Column("like_id", sa.String(), nullable=False),
        sa.Column("entry_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["agent_marketplace_entry.entry_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("like_id"),
    )
    op.create_index(
        op.f("ix_agent_marketplace_like_entry_id"),
        "agent_marketplace_like",
        ["entry_id"],
        unique=False,
    )
    op.create_index(
        "uq_agent_marketplace_like_active",
        "agent_marketplace_like",
        ["entry_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL"),
        sqlite_where=sa.text("removed_at IS NULL"),
    )
    op.create_table(
        "agent_marketplace_import",
        sa.Column("import_id", sa.String(), nullable=False),
        sa.Column("entry_id", sa.String(), nullable=False),
        sa.Column("target_team_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("agent_instance_id", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_instance_id"],
            ["agent_instance.agent_instance_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["agent_marketplace_entry.entry_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("import_id"),
    )
    op.create_index(
        op.f("ix_agent_marketplace_import_entry_id"),
        "agent_marketplace_import",
        ["entry_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_agent_marketplace_import_entry_id"),
        table_name="agent_marketplace_import",
    )
    op.drop_table("agent_marketplace_import")
    op.drop_index(
        "uq_agent_marketplace_like_active", table_name="agent_marketplace_like"
    )
    op.drop_index(
        op.f("ix_agent_marketplace_like_entry_id"), table_name="agent_marketplace_like"
    )
    op.drop_table("agent_marketplace_like")
    op.drop_table("agent_marketplace_entry_file")
    op.drop_index(
        op.f("ix_agent_marketplace_entry_team_id"),
        table_name="agent_marketplace_entry",
    )
    op.drop_table("agent_marketplace_entry")
