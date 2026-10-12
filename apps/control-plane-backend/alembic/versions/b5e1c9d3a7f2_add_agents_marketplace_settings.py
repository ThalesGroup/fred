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
"""add agents marketplace settings

The platform default (`platform_marketplace_settings`, at most one row keyed
`id="default"`, none seeded: absent = switch off, quota 5) and the two nullable
per-team overrides on `teammetadata` (null = the team follows the default).

Revision ID: b5e1c9d3a7f2
Revises: 93427a5fe874
Create Date: 2026-10-12 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5e1c9d3a7f2"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "93427a5fe874"  # pragma: allowlist secret
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

_QUOTA_CHECK = "ck_teammetadata_agents_publish_quota"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "platform_marketplace_settings",
        sa.Column("id", sa.String(), nullable=False, server_default="default"),
        sa.Column("agents_publishing_enabled", sa.Boolean(), nullable=False),
        sa.Column("agents_publish_quota", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "id = 'default'", name="ck_platform_marketplace_settings_singleton"
        ),
        sa.CheckConstraint(
            "agents_publish_quota >= 1",
            name="ck_platform_marketplace_settings_agents_publish_quota",
        ),
    )
    # Batch mode so SQLite (migration checks) can add the CHECK constraint.
    with op.batch_alter_table("teammetadata") as batch:
        batch.add_column(
            sa.Column("agents_publishing_enabled", sa.Boolean(), nullable=True)
        )
        batch.add_column(sa.Column("agents_publish_quota", sa.Integer(), nullable=True))
        batch.create_check_constraint(_QUOTA_CHECK, "agents_publish_quota >= 1")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("teammetadata") as batch:
        batch.drop_constraint(_QUOTA_CHECK, type_="check")
        batch.drop_column("agents_publish_quota")
        batch.drop_column("agents_publishing_enabled")
    op.drop_table("platform_marketplace_settings")
