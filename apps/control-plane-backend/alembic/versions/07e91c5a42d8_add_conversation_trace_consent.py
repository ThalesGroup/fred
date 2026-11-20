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

"""Record immutable conversation trace consent boundaries.

Revision ID: 07e91c5a42d8
Revises: 1d5e3fa6c20b
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "07e91c5a42d8"  # pragma: allowlist secret
down_revision = "1d5e3fa6c20b"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_trace_consent",
        sa.Column("grant_id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(),
            sa.ForeignKey("session_metadata.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("exchange_id", sa.String(255), nullable=False),
        sa.Column("first_rank", sa.Integer(), nullable=False),
        sa.Column("last_rank", sa.Integer(), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "uq_conversation_trace_active_consent",
        "conversation_trace_consent",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
        sqlite_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_conversation_trace_consent_session",
        "conversation_trace_consent",
        ["session_id"],
    )
    op.create_index(
        "ix_conversation_trace_consent_catalog",
        "conversation_trace_consent",
        ["granted_at", "grant_id"],
    )
    # The original singleton seeded false. An absent override now uses the profile default.
    settings = sa.table(
        "conversation_trace_settings",
        sa.column("id", sa.Integer),
        sa.column("enabled", sa.Boolean),
    )
    op.execute(
        settings.delete().where(settings.c.id == 1, settings.c.enabled.is_(False))
    )


def downgrade() -> None:
    op.drop_table("conversation_trace_consent")
