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

"""Add local user identity snapshots.

Revision ID: b4e8d2a9c613
Revises: 21e235382895
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4e8d2a9c613"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "21e235382895"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(), nullable=True))
    op.add_column("users", sa.Column("email", sa.String(), nullable=True))
    op.add_column("users", sa.Column("first_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(), nullable=True))
    op.add_column(
        "users", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_users_lower_username", "users", [sa.text("lower(username)")])


def downgrade() -> None:
    op.drop_index("ix_users_lower_username", table_name="users")
    op.drop_column("users", "last_seen_at")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
    op.drop_column("users", "email")
    op.drop_column("users", "username")
