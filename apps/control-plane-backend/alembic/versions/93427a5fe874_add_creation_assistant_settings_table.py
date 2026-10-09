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

"""add creation_assistant_settings table

Admin settings of the agent creation assistant: meta-prompt override and chat
model profile, both nullable (NULL = pod default), and the reasoning effort of
the assistant's own model call (off/low/medium/high, default off). Single
row keyed `id="default"`; no seed row.

Revision ID: 93427a5fe874
Revises: aac66348e27b
Create Date: 2026-10-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "93427a5fe874"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "aac66348e27b"  # pragma: allowlist secret
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
        "creation_assistant_settings",
        sa.Column("id", sa.String(), nullable=False, server_default="default"),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("model_profile_id", sa.String(), nullable=True),
        sa.Column(
            "reasoning_effort",
            sa.String(),
            nullable=False,
            server_default="off",
        ),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "id = 'default'", name="ck_creation_assistant_settings_singleton"
        ),
        sa.CheckConstraint(
            "reasoning_effort IN ('off', 'low', 'medium', 'high')",
            name="ck_creation_assistant_settings_reasoning_effort",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("creation_assistant_settings")
