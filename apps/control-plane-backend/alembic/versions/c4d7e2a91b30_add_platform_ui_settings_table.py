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
"""add platform_ui_settings table

Platform UI theme settings: the default UI theme and the theme ids hidden from
users. At most one row, keyed `id="default"` (CHECK constraint). No row is
seeded: absence means "never set", and the frontend then uses its own default.

Revision ID: c4d7e2a91b30
Revises: d7822fba0d40
Create Date: 2026-10-02 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d7e2a91b30"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "d7822fba0d40"  # pragma: allowlist secret
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
        "platform_ui_settings",
        sa.Column("id", sa.String(), nullable=False, server_default="default"),
        sa.Column("default_theme", sa.String(), nullable=True),
        sa.Column(
            "hidden_themes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id = 'default'", name="ck_platform_ui_settings_singleton"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("platform_ui_settings")
