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

"""add prompt table

Stores team-scoped prompt-library records owned by control-plane, including the
reserved ``personal`` team scope.

Revision ID: 9c4e1a2b3d4f
Revises: f1a2b3c4d5e6
Create Date: 2026-05-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c4e1a2b3d4f"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "f1a2b3c4d5e6"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "prompt",
        sa.Column("prompt_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("prompt_id"),
        sa.UniqueConstraint("team_id", "name", name="uq_prompt_team_name"),
    )
    op.create_index(op.f("ix_prompt_team_id"), "prompt", ["team_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f("ix_prompt_team_id"), table_name="prompt")
    op.drop_table("prompt")
