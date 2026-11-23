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
"""add home layout and featured home agents

`platform_ui_settings.home_layout` picks the home page mode ("classic" by
default, so existing platforms keep their home page) and
`home_ask_agent_instance_id` the agent behind its question field. The new
`platform_home_featured_agent` table holds the admin-ordered carousel agents.

Revision ID: e3a9c41f7b62
Revises: d7a2f591c034
Create Date: 2026-11-16 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3a9c41f7b62"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "d7a2f591c034"  # pragma: allowlist secret
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
    with op.batch_alter_table("platform_ui_settings") as batch:
        batch.add_column(
            sa.Column(
                "home_layout",
                sa.String(length=32),
                nullable=False,
                server_default="classic",
            )
        )
        batch.add_column(
            sa.Column("home_ask_agent_instance_id", sa.String(), nullable=True)
        )
        batch.create_foreign_key(
            "fk_platform_ui_settings_home_ask_agent",
            "agent_instance",
            ["home_ask_agent_instance_id"],
            ["agent_instance_id"],
            ondelete="SET NULL",
        )
    op.create_table(
        "platform_home_featured_agent",
        sa.Column("agent_instance_id", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("badge", sa.String(length=20), nullable=True),
        sa.Column(
            "highlights", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["agent_instance_id"],
            ["agent_instance.agent_instance_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("agent_instance_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("platform_home_featured_agent")
    with op.batch_alter_table("platform_ui_settings") as batch:
        batch.drop_constraint(
            "fk_platform_ui_settings_home_ask_agent", type_="foreignkey"
        )
        batch.drop_column("home_ask_agent_instance_id")
        batch.drop_column("home_layout")
