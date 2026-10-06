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
"""Store the accepted GCU version as text in users.

Revision ID: a7e9c2d41063
Revises: b4e8d2a9c613
"""

import sqlalchemy as sa
from alembic import op

revision = "a7e9c2d41063"  # pragma: allowlist secret
down_revision = "b4e8d2a9c613"  # pragma: allowlist secret
branch_labels = None
depends_on = None

__all__ = [
    "revision",
    "down_revision",
    "branch_labels",
    "depends_on",
    "upgrade",
    "downgrade",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "users",
            "gcuVersionAccepted",
            type_=sa.Text(),
            postgresql_using="CASE WHEN \"gcuVersionAccepted\"::text = 'V1' THEN 'v1' ELSE \"gcuVersionAccepted\"::text END",
        )
        sa.Enum("V1", name="gcu_version_type").drop(bind)
    else:
        with op.batch_alter_table("users") as batch:
            batch.alter_column(
                "gcuVersionAccepted",
                existing_type=sa.Enum("V1", name="gcu_version_type"),
                type_=sa.Text(),
                existing_nullable=True,
            )
        if bind.dialect.name == "sqlite":
            # SQLite table reflection omits the parent's expression index.
            op.create_index(
                "ix_users_lower_username", "users", [sa.text("lower(username)")]
            )
        op.execute(
            sa.text(
                "UPDATE users SET \"gcuVersionAccepted\" = 'v1' WHERE \"gcuVersionAccepted\" = 'V1'"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM users WHERE \"gcuVersionAccepted\" <> 'v1')"
        )
    ):
        raise RuntimeError(
            "Cannot downgrade GCU storage: accepted versions other than v1 would be lost"
        )
    legacy = sa.Enum("V1", name="gcu_version_type")
    if bind.dialect.name == "postgresql":
        legacy.create(bind)
        op.alter_column(
            "users",
            "gcuVersionAccepted",
            type_=legacy,
            postgresql_using="CASE WHEN \"gcuVersionAccepted\" = 'v1' THEN 'V1' ELSE \"gcuVersionAccepted\" END::gcu_version_type",
        )
    else:
        op.execute(
            sa.text(
                "UPDATE users SET \"gcuVersionAccepted\" = 'V1' WHERE \"gcuVersionAccepted\" = 'v1'"
            )
        )
        with op.batch_alter_table("users") as batch:
            batch.alter_column(
                "gcuVersionAccepted",
                existing_type=sa.Text(),
                type_=legacy,
                existing_nullable=True,
            )
        if bind.dialect.name == "sqlite":
            op.create_index(
                "ix_users_lower_username", "users", [sa.text("lower(username)")]
            )
