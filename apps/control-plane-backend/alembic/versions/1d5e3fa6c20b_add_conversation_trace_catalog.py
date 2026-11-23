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

"""Add the conversation trace catalog and deployment-wide capture settings.

Revision ID: 1d5e3fa6c20b
Revises: e3a9c41f7b62
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "1d5e3fa6c20b"  # pragma: allowlist secret
down_revision = "e3a9c41f7b62"  # pragma: allowlist secret
branch_labels = None
depends_on = None

__all__ = [
    "branch_labels",
    "depends_on",
    "down_revision",
    "downgrade",
    "revision",
    "upgrade",
]


def upgrade() -> None:
    settings = op.create_table(
        "conversation_trace_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.bulk_insert(settings, [{"id": 1, "enabled": False}])
    op.create_table(
        "conversation_trace_turn",
        sa.Column("capture_id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(),
            sa.ForeignKey("session_metadata.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("exchange_id", sa.String(255), nullable=False),
        sa.Column("runtime_id", sa.String(255), nullable=False),
        sa.Column("agent_display_name", sa.String(255), nullable=False),
        sa.Column("history_rank", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("turn_number", sa.Integer()),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("call_ids", sa.JSON(), nullable=False),
        sa.Column("trace_id", sa.String(32)),
        sa.Column("span_id", sa.String(16)),
        sa.UniqueConstraint(
            "session_id", "exchange_id", name="uq_conversation_trace_turn_exchange"
        ),
    )
    op.create_index(
        "ix_conversation_trace_turn_order",
        "conversation_trace_turn",
        ["session_id", "history_rank", "capture_id"],
    )
    op.create_index(
        "ix_conversation_trace_turn_catalog",
        "conversation_trace_turn",
        ["started_at", "capture_id"],
    )
    op.create_index(
        "ix_conversation_trace_turn_outcome_catalog",
        "conversation_trace_turn",
        ["outcome", "started_at", "capture_id"],
    )


def downgrade() -> None:
    op.drop_table("conversation_trace_turn")
    op.drop_table("conversation_trace_settings")
