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
"""Keep only the latest GCU acceptance in users.

Revision ID: e6b8d2a41074
Revises: a7e9c2d41063, b4e8d2a9c613
"""

import sqlalchemy as sa
from alembic import op

revision = "e6b8d2a41074"  # pragma: allowlist secret
down_revision = (
    "a7e9c2d41063",  # pragma: allowlist secret
    "b4e8d2a9c613",  # pragma: allowlist secret
)
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
    op.drop_table("user_gcu_acceptances")


def downgrade() -> None:
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
