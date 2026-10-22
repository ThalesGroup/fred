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

"""add disabled notification types

Creates `disabled_notification_types`: one row per notification type a
platform admin turned off. Empty means every type is sent, as before.

Revision ID: 83b81adf7450
Revises: 77cd5dc306cf
Create Date: 2026-10-22 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "83b81adf7450"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "77cd5dc306cf"  # pragma: allowlist secret
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
        "disabled_notification_types",
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("disabled_by", sa.String(), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("type"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("disabled_notification_types")
