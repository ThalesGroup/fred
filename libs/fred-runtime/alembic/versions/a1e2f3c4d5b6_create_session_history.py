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

"""create session_history table

Initial schema for the session_history table as originally deployed via
PostgresHistoryStore._ensure_tables (CREATE TABLE IF NOT EXISTS).

Stamp an existing production database that already has this table with:
    alembic stamp a1e2f3c4d5b6

Revision ID: a1e2f3c4d5b6
Revises:
Create Date: 2026-06-02 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1e2f3c4d5b6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "session_history",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column(
            "parts_json",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("session_id", "user_id", "rank"),
    )
    op.create_index(
        "ix_session_history_timestamp",
        "session_history",
        ["timestamp"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_session_history_timestamp", table_name="session_history")
    op.drop_table("session_history")
