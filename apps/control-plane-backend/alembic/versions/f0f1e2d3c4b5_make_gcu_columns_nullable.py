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

"""make gcu columns nullable

Revision ID: f0f1e2d3c4b5
Revises: ee5a5b163f34
Create Date: 2026-05-29 14:42:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0f1e2d3c4b5"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "ee5a5b163f34"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Using batch_alter_table is safe for both SQLite and PostgreSQL
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "gcuVersionAccepted",
            existing_type=sa.Enum("V1", name="gcu_version_type"),
            nullable=True,
        )
        batch_op.alter_column(
            "gcuAcceptedAt",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "gcuAcceptedAt",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
        batch_op.alter_column(
            "gcuVersionAccepted",
            existing_type=sa.Enum("V1", name="gcu_version_type"),
            nullable=False,
        )
