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
"""Persist GCU acceptance per configured version.

Revision ID: a7e9c2d41063
Revises: c4d7e2a91b30
"""

import sqlalchemy as sa
from alembic import op

revision = "a7e9c2d41063"  # pragma: allowlist secret
down_revision = "c4d7e2a91b30"  # pragma: allowlist secret
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
        op.execute(
            sa.text(
                "UPDATE users SET \"gcuVersionAccepted\" = 'v1' WHERE \"gcuVersionAccepted\" = 'V1'"
            )
        )
    op.create_table(
        "user_gcu_acceptances",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("version", sa.Text(), primary_key=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            'INSERT INTO user_gcu_acceptances (user_id, version, accepted_at) SELECT id, "gcuVersionAccepted", "gcuAcceptedAt" FROM users WHERE "gcuVersionAccepted" IS NOT NULL'
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM user_gcu_acceptances WHERE version <> 'v1' UNION ALL SELECT 1 FROM users WHERE \"gcuVersionAccepted\" <> 'v1')"
        )
    ):
        raise RuntimeError(
            "Cannot downgrade GCU storage: accepted versions other than v1 would be lost"
        )
    op.drop_table("user_gcu_acceptances")
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
