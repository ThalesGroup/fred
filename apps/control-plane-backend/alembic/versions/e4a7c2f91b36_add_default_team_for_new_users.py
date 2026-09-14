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

"""add default team for new users

A platform admin picks one team that every user joins on first GCU acceptance.
The partial unique index keeps at most one team flagged. Existing rows get
false: nothing changes until an admin chooses a team.

Revision ID: e4a7c2f91b36
Revises: d3f8a2c6e174
Create Date: 2026-09-14 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4a7c2f91b36"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "d3f8a2c6e174"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "uq_teammetadata_default_for_new_users"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "teammetadata",
        sa.Column(
            "is_default_for_new_users",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        _INDEX_NAME,
        "teammetadata",
        ["is_default_for_new_users"],
        unique=True,
        sqlite_where=sa.text("is_default_for_new_users"),
        postgresql_where=sa.text("is_default_for_new_users"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(_INDEX_NAME, table_name="teammetadata")
    # Batch mode: SQLite cannot drop a column in place.
    with op.batch_alter_table("teammetadata") as batch_op:
        batch_op.drop_column("is_default_for_new_users")
