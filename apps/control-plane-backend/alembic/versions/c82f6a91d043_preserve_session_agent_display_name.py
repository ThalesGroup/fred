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
"""Preserve conversation agent names after deletion.

Revision ID: c82f6a91d043
Revises: aac66348e27b
"""

import sqlalchemy as sa
from alembic import op

revision: str = "c82f6a91d043"  # pragma: allowlist secret
down_revision: str = "aac66348e27b"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "session_metadata",
        sa.Column("agent_display_name", sa.String(255), nullable=True),
    )
    sessions = sa.table(
        "session_metadata",
        sa.column("agent_instance_id", sa.String),
        sa.column("team_id", sa.String),
        sa.column("agent_display_name", sa.String(255)),
    )
    agents = sa.table(
        "agent_instance",
        sa.column("agent_instance_id", sa.String),
        sa.column("team_id", sa.String),
        sa.column("display_name", sa.String(255)),
    )
    name = sa.select(agents.c.display_name).where(
        agents.c.agent_instance_id == sessions.c.agent_instance_id,
        agents.c.team_id == sessions.c.team_id,
    )
    op.execute(sessions.update().values(agent_display_name=name.scalar_subquery()))


def downgrade() -> None:
    op.drop_column("session_metadata", "agent_display_name")
