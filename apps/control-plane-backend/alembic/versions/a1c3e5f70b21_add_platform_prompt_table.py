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

"""add platform_prompt table

Platform-wide platform prompt: the first block of every composed system prompt,
ahead of any agent's own template. At most one row ever
exists, always keyed `id="default"`, enforced by a CHECK constraint so the
store structurally cannot grow a second row.

No default row is written here. Row absence means "no admin has ever saved
one", and the runtime then falls back to the `platform_prompt` field of the
pod-shipped `config/platform_prompt.json`; a stored empty string is the distinct case of an
admin deliberately suppressing the block. Seeding a row at migration time
would erase that distinction and freeze today's default text into every
existing deployment's database.

Revision ID: a1c3e5f70b21
Revises: 0c70cb820802
Create Date: 2026-08-28 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c3e5f70b21"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "0c70cb820802"  # pragma: allowlist secret
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
        "platform_prompt",
        sa.Column("id", sa.String(), nullable=False, server_default="default"),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id = 'default'", name="ck_platform_prompt_singleton"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("platform_prompt")
