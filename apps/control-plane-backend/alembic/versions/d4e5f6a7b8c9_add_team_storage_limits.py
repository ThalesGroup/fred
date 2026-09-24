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

"""add team storage limit columns

Revision ID: d4e5f6a7b8c9
Revises: b3c4d5e6f7a8
Create Date: 2026-05-25 14:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "d6e7f8a9b0c1"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "teammetadata",
        sa.Column("max_resources_storage_size", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "teammetadata",
        sa.Column("current_resources_storage_size", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("teammetadata", "current_resources_storage_size")
    op.drop_column("teammetadata", "max_resources_storage_size")
